using System.Text.Json.Serialization;

namespace TendrilRoslyn.Models;

/// <summary>
/// Return type from resolve_value() when the key is found (resolved=true).
/// resolve_value() always applies the disambiguation tiebreak and returns one result.
/// </summary>
public sealed class ResolvedValue
{
    [JsonPropertyName("resolved")]
    public bool Resolved { get; init; } = true;

    [JsonPropertyName("value")]
    public string Value { get; init; } = "";

    /// <summary>The winning source locator (relative_path:key_or_line).</summary>
    [JsonPropertyName("source")]
    public string Source { get; init; } = "";

    /// <summary>Ordered locators from definition site to use site.</summary>
    [JsonPropertyName("def_use_chain")]
    public List<string> DefUseChain { get; init; } = new();

    /// <summary>1 = config-file; 2 = AST analysis.</summary>
    [JsonPropertyName("layer")]
    public int Layer { get; init; } = 1;
}
