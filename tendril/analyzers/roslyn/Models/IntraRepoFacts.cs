using System.Text.Json.Serialization;

namespace TendrilRoslyn.Models;

/// <summary>
/// Structured output of the analyze() RPC method.
/// Matches the IntraRepoFacts schema defined in specs/003-roslyn-intrarepo/data-model.md.
/// </summary>
public sealed class IntraRepoFacts
{
    /// <summary>Key → ordered list of source locators ("relative_path:key_or_line").</summary>
    [JsonPropertyName("def_use")]
    public Dictionary<string, List<string>> DefUse { get; init; } = new();

    /// <summary>Key → all known ValueSet entries (layer 1 and 2).</summary>
    [JsonPropertyName("value_sets")]
    public Dictionary<string, List<ValueSet>> ValueSets { get; init; } = new();

    /// <summary>Always null in M8 (reserved for future call-graph analysis).</summary>
    [JsonPropertyName("call_graph")]
    public object? CallGraph { get; init; } = null;

    /// <summary>
    /// True when layer-2 semantic analysis failed.
    /// Callers MUST treat layer-2 def-use chains as absent when this is true.
    /// </summary>
    [JsonPropertyName("partial_analysis")]
    public bool PartialAnalysis { get; set; } = false;

    /// <summary>True when response exceeded 10 MB and was truncated to top-N symbols.</summary>
    [JsonPropertyName("truncated")]
    public bool Truncated { get; set; } = false;

    /// <summary>Files or projects excluded due to parse/build/language errors.</summary>
    [JsonPropertyName("skipped_files")]
    public List<SkippedFile> SkippedFiles { get; init; } = new();
}
