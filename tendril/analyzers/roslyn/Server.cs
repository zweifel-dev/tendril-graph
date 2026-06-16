using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using TendrilRoslyn.Layer1;
using TendrilRoslyn.Layer2;
using TendrilRoslyn.Models;

namespace TendrilRoslyn;

/// <summary>
/// tendril-rpc/v1 JSON-RPC 2.0 server over stdin/stdout (FR-M8-001).
///
/// Protocol invariants:
///   - All diagnostic/log output goes to STDERR only — never stdout.
///   - Each response is one JSON line followed by FlushAsync().
///   - null from ReadLineAsync() == stdin EOF == clean shutdown (FR-M8-001 / CHK007).
/// </summary>
public static class Server
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public static async Task RunAsync(CancellationToken ct)
    {
        // Use raw streams to avoid Console.In/Out CRLF transformation (research.md §4)
        using var stdin  = new StreamReader(Console.OpenStandardInput(),
                               Encoding.UTF8, detectEncodingFromByteOrderMarks: false);
        using var stdout = new StreamWriter(Console.OpenStandardOutput(), Encoding.UTF8,
                               leaveOpen: true)
                           { AutoFlush = false };

        string? line;
        while ((line = await stdin.ReadLineAsync(ct)) is not null)
        {
            if (string.IsNullOrWhiteSpace(line)) continue;

            string? requestId = null;
            JsonObject response;
            try
            {
                var request = JsonNode.Parse(line) as JsonObject
                    ?? throw new InvalidOperationException("not a JSON object");

                requestId = request["id"]?.GetValue<string>();
                var method  = request["method"]?.GetValue<string>()
                    ?? throw new InvalidOperationException("missing method");
                var @params = request["params"] as JsonObject ?? new JsonObject();

                var result = await DispatchAsync(method, @params, ct);
                response   = JsonRpcSuccess(requestId, result);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (NotSupportedException ex)
            {
                response = JsonRpcError(requestId, -32601, "method not found", ex.Message);
            }
            catch (Exception ex)
            {
                response = JsonRpcError(requestId, -32603, "internal error", ex.Message);
            }

            await stdout.WriteLineAsync(response.ToJsonString());
            await stdout.FlushAsync(ct);   // CRITICAL: unblocks Python readline() (research.md §4)
        }
        // stdin returned null = EOF = Python closed stdin = clean teardown (CHK007)
    }

    // ── dispatcher ────────────────────────────────────────────────────────────

    private static async Task<JsonNode> DispatchAsync(
        string method, JsonObject @params, CancellationToken ct)
        => method switch
        {
            "handshake"     => HandleHandshake(@params),
            "analyze"       => await HandleAnalyzeAsync(@params, ct),
            "resolve_value" => await HandleResolveValueAsync(@params, ct),
            _               => throw new NotSupportedException(method),
        };

    // ── handshake ─────────────────────────────────────────────────────────────

    private static JsonNode HandleHandshake(JsonObject @params)
    {
        var clientVersion = @params["client_version"]?.GetValue<string>() ?? "";
        var compatible    = clientVersion == "1.0";
        return new JsonObject
        {
            ["server_version"] = "1.0",
            ["compatible"]     = compatible,
        };
    }

    // ── analyze ───────────────────────────────────────────────────────────────

    private static async Task<JsonNode> HandleAnalyzeAsync(
        JsonObject @params, CancellationToken ct)
    {
        var repoPath = @params["repo_path"]?.GetValue<string>()
            ?? throw new ArgumentException("missing repo_path");

        if (!Directory.Exists(repoPath))
            throw new DirectoryNotFoundException($"repo_path does not exist: {repoPath}");

        // Quick check: is this even a .NET repo?
        if (!IsDotNetRepo(repoPath))
        {
            // Return empty facts immediately (FR-M8-013)
            return SerializeFacts(new IntraRepoFacts());
        }

        var skippedFiles = new List<SkippedFile>();
        var defUse       = new Dictionary<string, List<string>>();
        var valueSets    = new Dictionary<string, List<ValueSet>>();

        // ── Layer 1: config-file parsing (always runs) ─────────────────────

        AddEntries(WebConfigParser.ParseAll(repoPath, skippedFiles),
                   defUse, valueSets);

        AddEntries(AppSettingsParser.ParseAll(repoPath, skippedFiles),
                   defUse, valueSets);

        // ── Layer 2a: syntactic analysis (always attempted) ────────────────

        AddEntries(SyntacticAnalyzer.AnalyzeAll(repoPath, skippedFiles),
                   defUse, valueSets);

        // ── Layer 2b: semantic analysis (attempted if MSBuild available) ───

        var partial = false;
        try
        {
            var semanticEntries = await SemanticAnalyzer.TryAnalyzeAsync(
                repoPath, skippedFiles, ct);
            AddEntries(semanticEntries, defUse, valueSets);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            // Semantic failure → partial_analysis=true; layer-1 results preserved
            partial = true;
            Console.Error.WriteLine($"[tendril] SemanticAnalyzer failed: {ex.Message}");
        }

        if (skippedFiles.Any(s =>
            s.Reason is "workspace-load-failed" or "nuget-restore-failed" or "build-failed"))
        {
            partial = true;
        }

        var facts = new IntraRepoFacts
        {
            CallGraph       = null,
            PartialAnalysis = partial,
            SkippedFiles    = skippedFiles,
        };
        facts.DefUse.AddRange(defUse);
        facts.ValueSets.AddRange(valueSets);

        // Enforce 10 MB truncation (FR-M8-014 / CHK034)
        ApplyTruncationIfNeeded(facts);

        return SerializeFacts(facts);
    }

    // ── resolve_value ─────────────────────────────────────────────────────────

    private static async Task<JsonNode> HandleResolveValueAsync(
        JsonObject @params, CancellationToken ct)
    {
        var repoPath = @params["repo_path"]?.GetValue<string>()
            ?? throw new ArgumentException("missing repo_path");
        var key = @params["key"]?.GetValue<string>()
            ?? throw new ArgumentException("missing key");

        if (!Directory.Exists(repoPath))
            throw new DirectoryNotFoundException($"repo_path does not exist: {repoPath}");

        // Run full analysis to get all candidates
        var analyzeNode = await HandleAnalyzeAsync(
            new JsonObject { ["repo_path"] = repoPath }, ct);

        var facts = JsonSerializer.Deserialize<IntraRepoFacts>(analyzeNode.ToJsonString(), JsonOpts);
        if (facts is null)
            return JsonSerializer.SerializeToNode(new Unresolved { Reason = "not-found" })!;

        if (!facts.ValueSets.TryGetValue(key, out var candidates) || candidates.Count == 0)
            return JsonSerializer.SerializeToNode(new Unresolved { Reason = "not-found" })!;

        // Disambiguation tiebreak (CHK031):
        //   1. Layer 2 over layer 1
        //   2. Most-specific config file (env-specific > base)
        //   3. Alphabetical on source locator
        var winner = candidates
            .OrderByDescending(v => v.Layer)
            .ThenByDescending(v => Specificity(v.Condition))
            .ThenBy(v => v.Source, StringComparer.Ordinal)
            .First();

        var defUseChain = facts.DefUse.TryGetValue(key, out var chain) ? chain : [winner.Source];

        return JsonSerializer.SerializeToNode(new ResolvedValue
        {
            Value      = winner.Value,
            Source     = winner.Source,
            DefUseChain = defUseChain,
            Layer      = winner.Layer,
        }, JsonOpts)!;
    }

    // ── helpers ───────────────────────────────────────────────────────────────

    private static bool IsDotNetRepo(string repoPath)
    {
        return Directory.EnumerateFiles(repoPath, "*.cs",          SearchOption.AllDirectories).Any()
            || Directory.EnumerateFiles(repoPath, "*.vb",          SearchOption.AllDirectories).Any()
            || Directory.EnumerateFiles(repoPath, "web.config",    SearchOption.AllDirectories).Any()
            || Directory.EnumerateFiles(repoPath, "appsettings*.json", SearchOption.AllDirectories).Any();
    }

    private static void AddEntries(
        IEnumerable<(string Key, ValueSet Entry)> entries,
        Dictionary<string, List<string>> defUse,
        Dictionary<string, List<ValueSet>> valueSets)
    {
        foreach (var (key, vs) in entries)
        {
            if (!valueSets.ContainsKey(key))
            {
                valueSets[key] = [];
                defUse[key]    = [];
            }
            valueSets[key].Add(vs);
            defUse[key].Add(vs.Source);
        }
    }

    private static int Specificity(string? condition)
    {
        if (condition is null) return 0;
        // More dots in filename = more specific (appsettings.prod.json > appsettings.json)
        return condition.Count(c => c == '.');
    }

    private static void ApplyTruncationIfNeeded(IntraRepoFacts facts)
    {
        const int MaxBytes = 10 * 1024 * 1024; // 10 MB

        var approxBytes = JsonSerializer.Serialize(facts, JsonOpts).Length;
        if (approxBytes <= MaxBytes) return;

        // Rank keys by reference count (number of def-use locators)
        var ranked = facts.DefUse
            .OrderByDescending(kv => kv.Value.Count)
            .Take(facts.DefUse.Count / 2)
            .Select(kv => kv.Key)
            .ToHashSet();

        var keysToRemove = facts.DefUse.Keys.Except(ranked).ToList();
        foreach (var k in keysToRemove)
        {
            facts.DefUse.Remove(k);
            facts.ValueSets.Remove(k);
        }
        facts.Truncated = true;
    }

    private static JsonNode SerializeFacts(IntraRepoFacts facts)
        => JsonSerializer.SerializeToNode(facts, JsonOpts)!;

    // ── JSON-RPC envelope helpers ─────────────────────────────────────────────

    private static JsonObject JsonRpcSuccess(string? id, JsonNode result)
        => new() { ["id"] = id, ["result"] = result };

    private static JsonObject JsonRpcError(
        string? id, int code, string message, string? detail = null)
        => new()
        {
            ["id"] = id,
            ["error"] = new JsonObject
            {
                ["code"]    = code,
                ["message"] = message,
                ["data"]    = detail is not null
                              ? new JsonObject { ["detail"] = detail }
                              : null,
            },
        };
}

// Extension helpers (needed since Dictionary doesn't have AddRange)
internal static class DictionaryExtensions
{
    public static void AddRange<TK, TV>(
        this Dictionary<TK, TV> dest, Dictionary<TK, TV> src)
        where TK : notnull
    {
        foreach (var kv in src)
            dest[kv.Key] = kv.Value;
    }
}
