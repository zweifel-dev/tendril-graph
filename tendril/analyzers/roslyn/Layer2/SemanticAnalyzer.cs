using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.MSBuild;
using TendrilRoslyn.Models;

namespace TendrilRoslyn.Layer2;

/// <summary>
/// Layer 2b: semantic analysis via MSBuildWorkspace — requires a compiled workspace.
/// Falls back gracefully when MSBuild/NuGet is unavailable (FR-M8-006 / CHK033).
/// MSBuildLocator.RegisterDefaults() MUST have been called before this class is loaded.
/// </summary>
public static class SemanticAnalyzer
{
    /// <summary>
    /// Attempt to open solution/projects under repoPath and extract cross-file const values.
    /// On failure, populates skippedFiles and sets partial=true.
    /// </summary>
    public static async Task<IEnumerable<(string Key, ValueSet Entry)>> TryAnalyzeAsync(
        string repoPath,
        List<SkippedFile> skippedFiles,
        CancellationToken ct)
    {
        if (!MSBuildLocator.CanRegister && !MSBuildLocator.IsRegistered)
        {
            // MSBuild not available on this host — layer 2b unavailable
            skippedFiles.Add(new SkippedFile
            {
                Path = repoPath,
                Reason = "workspace-load-failed",
            });
            Console.Error.WriteLine("[tendril] SemanticAnalyzer: MSBuild not available");
            return [];
        }

        // Find solution files first; fall back to .csproj files
        var solutionFiles = Directory.EnumerateFiles(repoPath, "*.sln",
            SearchOption.AllDirectories).ToList();

        if (solutionFiles.Count == 0)
        {
            // No solution — nothing to load semantically
            return [];
        }

        var results = new List<(string Key, ValueSet Entry)>();

        foreach (var solutionPath in solutionFiles)
        {
            var relSln = Path.GetRelativePath(repoPath, solutionPath).Replace('\\', '/');
            try
            {
                using var workspace = MSBuildWorkspace.Create();
                var solution = await workspace.OpenSolutionAsync(solutionPath,
                    progress: null, cancellationToken: ct);

                // Check for workspace-level failures (CHK033)
                var failures = workspace.Diagnostics
                    .Where(d => d.Kind == WorkspaceDiagnosticKind.Failure)
                    .ToList();

                foreach (var failure in failures)
                {
                    var msg = failure.Message ?? "";
                    var reason = ClassifyFailureReason(msg);
                    var projectPath = msg.Length > 0 ? msg : relSln;
                    skippedFiles.Add(new SkippedFile
                    {
                        Path = Path.GetRelativePath(repoPath, projectPath).Replace('\\', '/'),
                        Reason = reason,
                    });
                    Console.Error.WriteLine($"[tendril] SemanticAnalyzer: workspace failure: {msg}");
                }

                // Extract from projects that did load
                foreach (var project in solution.Projects)
                {
                    if (project.Language != LanguageNames.CSharp
                        && project.Language != LanguageNames.VisualBasic)
                    {
                        skippedFiles.Add(new SkippedFile
                        {
                            Path = Path.GetRelativePath(repoPath,
                                       project.FilePath ?? project.Name).Replace('\\', '/'),
                            Reason = "unsupported-language",
                        });
                        continue;
                    }

                    Compilation? compilation;
                    try
                    {
                        compilation = await project.GetCompilationAsync(ct);
                    }
                    catch
                    {
                        skippedFiles.Add(new SkippedFile
                        {
                            Path = Path.GetRelativePath(repoPath,
                                       project.FilePath ?? project.Name).Replace('\\', '/'),
                            Reason = "build-failed",
                        });
                        continue;
                    }

                    if (compilation is null)
                        continue;

                    // Walk all named types for const fields
                    foreach (var symbol in GetAllTypes(compilation.GlobalNamespace))
                    {
                        foreach (var member in symbol.GetMembers()
                            .OfType<IFieldSymbol>()
                            .Where(f => f.IsConst && f.ConstantValue is string))
                        {
                            var strValue = (string)f.ConstantValue!;
                            var locs = member.Locations;
                            if (locs.IsEmpty) continue;
                            var loc = locs[0];
                            if (!loc.IsInSource) continue;

                            var lineSpan = loc.GetLineSpan();
                            var filePath = lineSpan.Path;
                            var relPath = filePath.Length > 0
                                ? Path.GetRelativePath(repoPath, filePath).Replace('\\', '/')
                                : "";
                            var line = lineSpan.StartLinePosition.Line + 1;

                            results.Add((member.Name, new ValueSet
                            {
                                Value     = strValue,
                                Source    = $"{relPath}:{line}",
                                Condition = null,
                                Layer     = 2,
                            }));
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                var reason = ClassifyFailureReason(ex.Message);
                skippedFiles.Add(new SkippedFile { Path = relSln, Reason = reason });
                Console.Error.WriteLine($"[tendril] SemanticAnalyzer: exception on {relSln}: {ex.Message}");
            }
        }

        return results;

        // Local function — fixes CS0165 (use of unassigned local variable)
        static string ClassifyFailureReason(string message)
        {
            var lower = message.ToLowerInvariant();
            if (lower.Contains("nuget") || lower.Contains("restore"))
                return "nuget-restore-failed";
            if (lower.Contains("build") || lower.Contains("compil"))
                return "build-failed";
            return "workspace-load-failed";
        }
    }

    private static IEnumerable<INamedTypeSymbol> GetAllTypes(INamespaceSymbol ns)
    {
        foreach (var type in ns.GetTypeMembers())
        {
            yield return type;
            foreach (var nested in GetNestedTypes(type))
                yield return nested;
        }
        foreach (var child in ns.GetNamespaceMembers())
            foreach (var t in GetAllTypes(child))
                yield return t;
    }

    private static IEnumerable<INamedTypeSymbol> GetNestedTypes(INamedTypeSymbol type)
    {
        foreach (var nested in type.GetTypeMembers())
        {
            yield return nested;
            foreach (var t in GetNestedTypes(nested))
                yield return t;
        }
    }
}
