using System.Text.Json.Serialization;

namespace TendrilRoslyn.Models;

/// <summary>
/// Records a file or project that was excluded from analysis.
/// </summary>
public sealed class SkippedFile
{
    /// <summary>Path relative to repo_path.</summary>
    [JsonPropertyName("path")]
    public string Path { get; init; } = "";

    /// <summary>
    /// Reason for exclusion; uses same enum as Unresolved.Reason plus
    /// "unsupported-language" for non-C#/VB.NET projects.
    /// </summary>
    [JsonPropertyName("reason")]
    public string Reason { get; init; } = "parse-error";
}
