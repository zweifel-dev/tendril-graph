using System.Xml.Linq;
using TendrilRoslyn.Models;

namespace TendrilRoslyn.Layer1;

/// <summary>
/// Parses web.config &lt;appSettings&gt; entries (FR-M8-006 / layer 1).
/// Uses XDocument for LINQ-friendly null-safe attribute access.
/// No MSBuild dependency — always runs.
/// </summary>
public static class WebConfigParser
{
    /// <summary>
    /// Enumerates all web.config files under repoPath and yields layer-1 entries.
    /// </summary>
    public static IEnumerable<(string Key, ValueSet Entry)> ParseAll(
        string repoPath, List<SkippedFile> skippedFiles)
    {
        var webConfigs = Directory.EnumerateFiles(
            repoPath, "web.config", SearchOption.AllDirectories);

        foreach (var filePath in webConfigs)
        {
            var relative = Path.GetRelativePath(repoPath, filePath)
                               .Replace('\\', '/');

            foreach (var entry in ParseFile(filePath, relative, skippedFiles))
                yield return entry;
        }
    }

    private static IEnumerable<(string Key, ValueSet Entry)> ParseFile(
        string filePath, string relative, List<SkippedFile> skippedFiles)
    {
        XDocument doc;
        try
        {
            doc = XDocument.Load(filePath);
        }
        catch (Exception ex)
        {
            skippedFiles.Add(new SkippedFile { Path = relative, Reason = "parse-error" });
            Console.Error.WriteLine($"[tendril] WebConfigParser: skipping {relative}: {ex.Message}");
            yield break;
        }

        var appSettings = doc.Root?
            .Descendants("appSettings")
            .FirstOrDefault();

        if (appSettings is null)
            yield break;

        foreach (var add in appSettings.Elements("add"))
        {
            var key   = (string?)add.Attribute("key");
            var value = (string?)add.Attribute("value");

            if (key is null || value is null)
                continue;

            var source = $"{relative}:{key}";
            yield return (key, new ValueSet
            {
                Value     = value,
                Source    = source,
                Condition = null,   // web.config entries are unconditional (CHK004)
                Layer     = 1,
            });
        }
    }
}
