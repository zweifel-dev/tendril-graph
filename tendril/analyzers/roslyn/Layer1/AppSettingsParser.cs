using System.Text.Json;
using TendrilRoslyn.Models;

namespace TendrilRoslyn.Layer1;

/// <summary>
/// Parses appsettings*.json files using System.Text.Json (FR-M8-006 / layer 1).
/// Flattens nested JSON with ":" separator to match ASP.NET Core IConfiguration key paths.
/// Non-string values are coerced to string (CHK029).
/// </summary>
public static class AppSettingsParser
{
    /// <summary>
    /// Enumerates appsettings*.json files under repoPath and yields layer-1 entries.
    /// Files are processed in order of specificity (base → env-specific).
    /// </summary>
    public static IEnumerable<(string Key, ValueSet Entry)> ParseAll(
        string repoPath, List<SkippedFile> skippedFiles)
    {
        // Enumerate base files first, then environment-specific overrides
        var allFiles = Directory.EnumerateFiles(
                repoPath, "appsettings*.json", SearchOption.AllDirectories)
            .OrderBy(f => SpecificityRank(Path.GetFileName(f)))
            .ThenBy(f => f);

        foreach (var filePath in allFiles)
        {
            var relative = Path.GetRelativePath(repoPath, filePath)
                               .Replace('\\', '/');
            var fileName = Path.GetFileName(filePath);
            // condition = null for base file; basename for env-specific files (CHK004)
            var condition = IsBaseFile(fileName) ? null : fileName;

            foreach (var entry in ParseFile(filePath, relative, condition, skippedFiles))
                yield return entry;
        }
    }

    private static bool IsBaseFile(string fileName)
        => string.Equals(fileName, "appsettings.json", StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// Lower rank = processed first (base before env-specific).
    /// </summary>
    private static int SpecificityRank(string fileName)
    {
        // "appsettings.json" is the base (rank 0); others rank by part count
        var parts = Path.GetFileNameWithoutExtension(fileName)
                        .Split('.', StringSplitOptions.RemoveEmptyEntries);
        return parts.Length;
    }

    private static IEnumerable<(string Key, ValueSet Entry)> ParseFile(
        string filePath, string relative, string? condition,
        List<SkippedFile> skippedFiles)
    {
        JsonDocument doc;
        try
        {
            using var stream = File.OpenRead(filePath);
            doc = JsonDocument.Parse(stream);
        }
        catch (Exception ex)
        {
            skippedFiles.Add(new SkippedFile { Path = relative, Reason = "parse-error" });
            Console.Error.WriteLine($"[tendril] AppSettingsParser: skipping {relative}: {ex.Message}");
            yield break;
        }

        using (doc)
        {
            foreach (var (flatKey, strValue) in FlattenJson(doc.RootElement, prefix: ""))
            {
                var source = $"{relative}:{flatKey}";
                yield return (flatKey, new ValueSet
                {
                    Value     = strValue,
                    Source    = source,
                    Condition = condition,
                    Layer     = 1,
                });
            }
        }
    }

    /// <summary>
    /// Recursively flatten a JSON element using ":" as the key separator,
    /// consistent with ASP.NET Core IConfiguration key paths.
    /// Non-string values are coerced to their string representation (CHK029).
    /// </summary>
    private static IEnumerable<(string Key, string Value)> FlattenJson(
        JsonElement element, string prefix)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (var prop in element.EnumerateObject())
            {
                var fullKey = prefix.Length > 0
                    ? $"{prefix}:{prop.Name}"
                    : prop.Name;
                foreach (var pair in FlattenJson(prop.Value, fullKey))
                    yield return pair;
            }
        }
        else
        {
            // Coerce non-string values to string (CHK029)
            var strValue = element.ValueKind switch
            {
                JsonValueKind.String => element.GetString() ?? "",
                JsonValueKind.Number => element.GetRawText(),
                JsonValueKind.True   => "true",
                JsonValueKind.False  => "false",
                JsonValueKind.Null   => "",
                _                    => element.GetRawText(),
            };
            yield return (prefix, strValue);
        }
    }
}
