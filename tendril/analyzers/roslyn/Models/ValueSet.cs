using System.Text.Json.Serialization;

namespace TendrilRoslyn.Models;

/// <summary>
/// One entry in IntraRepoFacts.value_sets[key].
/// Represents a single known value for a key from a single source and layer.
/// </summary>
public sealed class ValueSet
{
    /// <summary>The resolved string value (non-string JSON values are coerced to string).</summary>
    [JsonPropertyName("value")]
    public string Value { get; init; } = "";

    /// <summary>Source locator: "relative_path:key_or_line".</summary>
    [JsonPropertyName("source")]
    public string Source { get; init; } = "";

    /// <summary>
    /// Basename of the most-specific config file, or null for unconditional values.
    /// e.g. "appsettings.prod.json" or null for web.config / appsettings.json base.
    /// </summary>
    [JsonPropertyName("condition")]
    public string? Condition { get; init; } = null;

    /// <summary>1 = config-file parsing (layer 1); 2 = C# AST analysis (layer 2).</summary>
    [JsonPropertyName("layer")]
    public int Layer { get; init; } = 1;
}
