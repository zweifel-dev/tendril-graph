using System.Text.Json.Serialization;

namespace TendrilRoslyn.Models;

/// <summary>
/// Return type from resolve_value() when resolution fails (resolved=false).
/// Never fabricates a value — emits a typed reason instead (FR-M8-005 / CHK018).
/// </summary>
public sealed class Unresolved
{
    [JsonPropertyName("resolved")]
    public bool Resolved { get; init; } = false;

    /// <summary>
    /// Typed failure reason (CHK018 / CHK033):
    ///   "not-found"              — key absent from all layers
    ///   "dynamic-value"          — key found but value is a runtime expression
    ///   "is-secret"              — key matched a redact pattern (Python-side filter)
    ///   "build-failed"           — C# compilation failed
    ///   "parse-error"            — config file could not be parsed
    ///   "nuget-restore-failed"   — NuGet package restore failed
    ///   "workspace-load-failed"  — MSBuild project/solution load failed
    /// </summary>
    [JsonPropertyName("reason")]
    public string Reason { get; init; } = "not-found";

    [JsonPropertyName("detail")]
    public string? Detail { get; init; } = null;
}
