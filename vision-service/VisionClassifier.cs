// VisionClassifier — wraps Phi Silica ImageDescriptionGenerator
// Provides describe, classify, and extract-text operations

using System.Text.Json;
using System.Text.RegularExpressions;
using System.Runtime.InteropServices.WindowsRuntime;

#if WINDOWS
using Microsoft.Graphics.Imaging;
using Microsoft.Windows.AI;
using Microsoft.Windows.AI.Imaging;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;
#endif

public static class VisionClassifier
{
    public static bool IsAvailable { get; private set; } = false;

    // Constrained categories for field inspection (matches build spec)
    private static readonly string[] InspectionCategories = new[]
    {
        "Water Damage",
        "Structural Crack",
        "Mold",
        "Electrical Hazard",
        "Trip Hazard"
    };

#if WINDOWS
    private static ImageDescriptionGenerator? _generator;
#endif

    public static async Task InitializeAsync()
    {
#if WINDOWS
        try
        {
            // Check if the Phi Silica vision model is available
            var readyState = ImageDescriptionGenerator.GetReadyState();
            if (readyState == AIFeatureReadyState.NotReady)
            {
                Console.WriteLine("[VisionClassifier] Model not ready, calling EnsureReadyAsync...");
                var readyResult = await ImageDescriptionGenerator.EnsureReadyAsync();
                if (readyResult.Status != AIFeatureReadyResultState.Success)
                {
                    Console.WriteLine($"[VisionClassifier] EnsureReadyAsync failed: {readyResult.Status}");
                    Console.WriteLine($"[VisionClassifier] Error: {readyResult.ExtendedError?.Message}");
                    IsAvailable = false;
                    return;
                }
            }

            _generator = await ImageDescriptionGenerator.CreateAsync();
            IsAvailable = true;
            Console.WriteLine("[VisionClassifier] Phi Silica Vision initialized successfully");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[VisionClassifier] Initialization failed: {ex.Message}");
            Console.WriteLine("[VisionClassifier] This is expected if Phi Silica model is not installed");
            Console.WriteLine("[VisionClassifier] or LAF token is not configured.");
            IsAvailable = false;
        }
#else
        Console.WriteLine("[VisionClassifier] Not running on Windows — Phi Silica unavailable");
        IsAvailable = false;
        await Task.CompletedTask;
#endif
    }

    /// <summary>
    /// General image description using Phi Silica Vision.
    /// </summary>
    public static async Task<object> DescribeAsync(byte[] imageBytes, string kind = "detailed")
    {
#if WINDOWS
        if (_generator == null)
            return new { error = "Vision model not initialized" };

        try
        {
            var imageBuffer = await BytesToImageBuffer(imageBytes);

            var descKind = kind.ToLower() switch
            {
                "brief" => ImageDescriptionKind.BriefDescription,
                "detailed" => ImageDescriptionKind.DetailedDescription,
                "diagram" => ImageDescriptionKind.DiagramDescription,
                "accessible" => ImageDescriptionKind.AccessibleDescription,
                _ => ImageDescriptionKind.DetailedDescription
            };

            var result = await _generator.DescribeAsync(imageBuffer, descKind, null);

            if (result.Status == ImageDescriptionResultStatus.Complete)
            {
                return new
                {
                    description = result.Description,
                    kind = kind,
                    status = "complete"
                };
            }
            else
            {
                return new
                {
                    error = $"Description failed: {result.Status}",
                    status = result.Status.ToString()
                };
            }
        }
        catch (Exception ex)
        {
            return new { error = ex.Message };
        }
#else
        await Task.CompletedTask;
        return new { error = "Phi Silica not available on this platform" };
#endif
    }

    /// <summary>
    /// Classify an image into constrained inspection categories.
    /// Uses Phi Silica detailed description, then maps to categories + severity.
    /// </summary>
    public static async Task<object> ClassifyAsync(byte[] imageBytes)
    {
#if WINDOWS
        if (_generator == null)
            return new { error = "Vision model not initialized" };

        try
        {
            var imageBuffer = await BytesToImageBuffer(imageBytes);

            // Get a detailed description from Phi Silica
            var result = await _generator.DescribeAsync(
                imageBuffer,
                ImageDescriptionKind.DetailedDescription,
                null
            );

            if (result.Status != ImageDescriptionResultStatus.Complete)
            {
                return new
                {
                    error = $"Image analysis failed: {result.Status}",
                    status = result.Status.ToString()
                };
            }

            var description = result.Description;

            // Map description to constrained category + severity + confidence
            var classification = MapToInspectionCategory(description);

            return new
            {
                category = classification.Category,
                severity = classification.Severity,
                confidence = classification.Confidence,
                explanation = classification.Explanation,
                raw_description = description,
                status = "complete"
            };
        }
        catch (Exception ex)
        {
            return new { error = ex.Message };
        }
#else
        await Task.CompletedTask;
        return new { error = "Phi Silica not available on this platform" };
#endif
    }

    /// <summary>
    /// Extract handwritten text from an ink overlay image.
    /// </summary>
    public static async Task<object> ExtractTextAsync(byte[] imageBytes)
    {
#if WINDOWS
        if (_generator == null)
            return new { error = "Vision model not initialized" };

        try
        {
            var imageBuffer = await BytesToImageBuffer(imageBytes);

            // Use detailed description to capture any text in the image
            var result = await _generator.DescribeAsync(
                imageBuffer,
                ImageDescriptionKind.DetailedDescription,
                null
            );

            if (result.Status == ImageDescriptionResultStatus.Complete)
            {
                return new
                {
                    extracted_text = result.Description,
                    status = "complete"
                };
            }
            else if (result.Status == ImageDescriptionResultStatus.ImageHasTooMuchText)
            {
                // This status actually means there IS text — try accessible mode
                var retryResult = await _generator.DescribeAsync(
                    imageBuffer,
                    ImageDescriptionKind.AccessibleDescription,
                    null
                );

                return new
                {
                    extracted_text = retryResult.Status == ImageDescriptionResultStatus.Complete
                        ? retryResult.Description
                        : "Text detected but could not be fully extracted",
                    status = retryResult.Status.ToString()
                };
            }
            else
            {
                return new
                {
                    extracted_text = "No text detected",
                    status = result.Status.ToString()
                };
            }
        }
        catch (Exception ex)
        {
            return new { error = ex.Message };
        }
#else
        await Task.CompletedTask;
        return new { error = "Phi Silica not available on this platform" };
#endif
    }

#if WINDOWS
    /// <summary>
    /// Convert raw image bytes to ImageBuffer via SoftwareBitmap.
    /// </summary>
    private static async Task<ImageBuffer> BytesToImageBuffer(byte[] imageBytes)
    {
        using var memStream = new InMemoryRandomAccessStream();
        await memStream.WriteAsync(imageBytes.AsBuffer());
        memStream.Seek(0);

        var decoder = await BitmapDecoder.CreateAsync(memStream);
        var softwareBitmap = await decoder.GetSoftwareBitmapAsync(
            BitmapPixelFormat.Bgra8,
            BitmapAlphaMode.Premultiplied
        );

        return ImageBuffer.CreateForSoftwareBitmap(softwareBitmap);
    }
#endif

    /// <summary>
    /// Map a free-text image description to constrained inspection categories.
    /// Uses keyword matching against the Phi Silica description to produce
    /// a structured classification with category, severity, and confidence.
    /// </summary>
    private static InspectionClassification MapToInspectionCategory(string description)
    {
        var lower = description.ToLower();

        // Score each category based on keyword presence
        var scores = new Dictionary<string, int>
        {
            ["Water Damage"] = ScoreKeywords(lower,
                "water", "moisture", "wet", "damp", "leak", "drip", "stain",
                "discoloration", "puddle", "flood", "seepage", "condensation",
                "water damage", "water stain", "pipe"),
            ["Structural Crack"] = ScoreKeywords(lower,
                "crack", "fracture", "split", "gap", "separation", "broken",
                "structural", "foundation", "wall crack", "concrete", "fissure",
                "settlement", "shift"),
            ["Mold"] = ScoreKeywords(lower,
                "mold", "mould", "fungus", "fungi", "spore", "mildew",
                "black spot", "growth", "organic", "damp growth", "discolored patch"),
            ["Electrical Hazard"] = ScoreKeywords(lower,
                "wire", "wiring", "electrical", "spark", "outlet", "exposed wire",
                "cable", "panel", "circuit", "burn mark", "scorch", "socket",
                "voltage", "power"),
            ["Trip Hazard"] = ScoreKeywords(lower,
                "trip", "uneven", "raised", "loose", "broken tile", "carpet",
                "threshold", "step", "obstacle", "floor", "surface", "tripping",
                "gap", "hole", "damaged floor")
        };

        // Find best match
        var bestCategory = "Water Damage"; // default
        var bestScore = 0;
        foreach (var kvp in scores)
        {
            if (kvp.Value > bestScore)
            {
                bestScore = kvp.Value;
                bestCategory = kvp.Key;
            }
        }

        // Derive confidence from score strength (0-100)
        var confidence = bestScore switch
        {
            >= 5 => Math.Min(95, 70 + bestScore * 3),
            >= 3 => 65 + bestScore * 3,
            >= 1 => 50 + bestScore * 10,
            _ => 40 // no keywords matched — low confidence
        };

        // Derive severity from confidence + category risk weight
        var severity = (bestCategory, confidence) switch
        {
            ("Electrical Hazard", >= 70) => "Critical",
            ("Electrical Hazard", _) => "High",
            ("Structural Crack", >= 80) => "High",
            ("Mold", >= 80) => "High",
            (_, >= 85) => "High",
            (_, >= 65) => "Moderate",
            _ => "Low"
        };

        // Build explanation from the description (first sentence or first 120 chars)
        var explanation = description.Length > 120
            ? description[..120].TrimEnd() + "..."
            : description;

        // Try to use just the first sentence
        var firstSentenceEnd = description.IndexOfAny(new[] { '.', '!', '?' });
        if (firstSentenceEnd > 0 && firstSentenceEnd < 150)
            explanation = description[..(firstSentenceEnd + 1)];

        return new InspectionClassification
        {
            Category = bestCategory,
            Severity = severity,
            Confidence = Math.Min(confidence, 100),
            Explanation = explanation
        };
    }

    private static int ScoreKeywords(string text, params string[] keywords)
    {
        int score = 0;
        foreach (var kw in keywords)
        {
            if (text.Contains(kw))
                score++;
        }
        return score;
    }
}

public record InspectionClassification
{
    public string Category { get; init; } = "";
    public string Severity { get; init; } = "";
    public int Confidence { get; init; }
    public string Explanation { get; init; } = "";
}
