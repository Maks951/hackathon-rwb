using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

public sealed class RunnerContractTests
{
    private static string Normalize(string path) => Regex.Replace(path.TrimEnd('/'), @"\{([^}:]+):[^}]+\}", "{$1}").ToLowerInvariant();
    [Fact]
    public void RuntimeRoutesMatchGeneratedContract()
    {
        using var factory = new WebApplicationFactory<Program>();
        using var client = factory.CreateClient();
        var source = factory.Services.GetRequiredService<EndpointDataSource>();
        var actual = source.Endpoints.OfType<RouteEndpoint>()
            .SelectMany(e => (e.Metadata.GetMetadata<HttpMethodMetadata>()?.HttpMethods ?? Array.Empty<string>())
            .Select(m => m.ToUpperInvariant()+" "+Normalize(e.RoutePattern.RawText ?? "")))
            .Where(p => p.Contains(" /api/v1/")).ToHashSet();
        using var spec = JsonDocument.Parse(File.ReadAllText("/work/product/generated-api.json"));
        var expected = spec.RootElement.GetProperty("endpoints").EnumerateArray()
            .Select(e => e.GetProperty("method").GetString()!.ToUpperInvariant()+" "+Normalize(e.GetProperty("path").GetString()!))
            .ToHashSet();
        Assert.NotEmpty(expected);
        Assert.True(expected.SetEquals(actual), "Runtime route/method set differs from generated-api.json. Missing: "
            +string.Join(", ",expected.Except(actual))+"; Extra: "+string.Join(", ",actual.Except(expected)));
    }
}
