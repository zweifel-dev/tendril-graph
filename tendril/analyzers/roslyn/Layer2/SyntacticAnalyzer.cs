using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using TendrilRoslyn.Models;

namespace TendrilRoslyn.Layer2;

/// <summary>
/// Layer 2a: syntactic analysis of .cs/.vb files — no build, no workspace required.
/// Extracts string literal values from const declarations, field initializers,
/// and property default values (FR-M8-006 / CHK013).
/// </summary>
public static class SyntacticAnalyzer
{
    /// <summary>
    /// Walk all .cs files under repoPath and extract compile-time string literals.
    /// Returns (identifier, ValueSet) pairs with layer=2 and line-number source locators.
    /// </summary>
    public static IEnumerable<(string Key, ValueSet Entry)> AnalyzeAll(
        string repoPath, List<SkippedFile> skippedFiles)
    {
        var csFiles = Directory.EnumerateFiles(
            repoPath, "*.cs", SearchOption.AllDirectories);

        foreach (var filePath in csFiles)
        {
            var relative = Path.GetRelativePath(repoPath, filePath)
                               .Replace('\\', '/');
            string text;
            try
            {
                text = File.ReadAllText(filePath);
            }
            catch (Exception ex)
            {
                skippedFiles.Add(new SkippedFile { Path = relative, Reason = "parse-error" });
                Console.Error.WriteLine($"[tendril] SyntacticAnalyzer: skipping {relative}: {ex.Message}");
                continue;
            }

            SyntaxTree tree;
            try
            {
                tree = CSharpSyntaxTree.ParseText(text, path: filePath);
            }
            catch (Exception ex)
            {
                skippedFiles.Add(new SkippedFile { Path = relative, Reason = "parse-error" });
                Console.Error.WriteLine($"[tendril] SyntacticAnalyzer: parse failed {relative}: {ex.Message}");
                continue;
            }

            var root = tree.GetRoot();

            // const fields: private const string ServiceUrl = "https://...";
            foreach (var fieldDecl in root.DescendantNodes().OfType<FieldDeclarationSyntax>()
                .Where(f => f.Modifiers.Any(SyntaxKind.ConstKeyword)))
            {
                foreach (var variable in fieldDecl.Declaration.Variables)
                {
                    if (variable.Initializer?.Value is LiteralExpressionSyntax lit
                        && lit.IsKind(SyntaxKind.StringLiteralExpression))
                    {
                        var line = tree.GetLineSpan(variable.Span).StartLinePosition.Line + 1;
                        var source = $"{relative}:{line}";
                        yield return (variable.Identifier.Text, new ValueSet
                        {
                            Value     = lit.Token.ValueText,
                            Source    = source,
                            Condition = null,
                            Layer     = 2,
                        });
                    }
                }
            }

            // const locals: const string Url = "...";
            foreach (var localDecl in root.DescendantNodes().OfType<LocalDeclarationStatementSyntax>()
                .Where(l => l.Modifiers.Any(SyntaxKind.ConstKeyword)))
            {
                foreach (var variable in localDecl.Declaration.Variables)
                {
                    if (variable.Initializer?.Value is LiteralExpressionSyntax lit
                        && lit.IsKind(SyntaxKind.StringLiteralExpression))
                    {
                        var line = tree.GetLineSpan(variable.Span).StartLinePosition.Line + 1;
                        var source = $"{relative}:{line}";
                        yield return (variable.Identifier.Text, new ValueSet
                        {
                            Value     = lit.Token.ValueText,
                            Source    = source,
                            Condition = null,
                            Layer     = 2,
                        });
                    }
                }
            }

            // property defaults: public string Url { get; } = "...";
            foreach (var propDecl in root.DescendantNodes().OfType<PropertyDeclarationSyntax>())
            {
                if (propDecl.Initializer?.Value is LiteralExpressionSyntax lit
                    && lit.IsKind(SyntaxKind.StringLiteralExpression))
                {
                    var line = tree.GetLineSpan(propDecl.Span).StartLinePosition.Line + 1;
                    var source = $"{relative}:{line}";
                    yield return (propDecl.Identifier.Text, new ValueSet
                    {
                        Value     = lit.Token.ValueText,
                        Source    = source,
                        Condition = null,
                        Layer     = 2,
                    });
                }
            }
        }
    }
}
