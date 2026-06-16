// TendrilRoslyn — tendril-rpc/v1 server (M8)
// CRITICAL: MSBuildLocator.RegisterDefaults() MUST be the first call in Main(),
// before any Microsoft.Build.* or Microsoft.CodeAnalysis.MSBuild.* type is loaded.
// Violating this load-order causes TypeLoadException at runtime (research.md §2).

using Microsoft.Build.Locator;
using TendrilRoslyn;

if (MSBuildLocator.CanRegister)
    MSBuildLocator.RegisterDefaults();

await Server.RunAsync(CancellationToken.None);
