using Generated.Api.Contracts;
using Generated.Api.Data;
using Generated.Api.Infrastructure;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<SafeExceptionHandler>();
builder.Services.AddDbContext<ProductDbContext>((services, options) =>
{
    var configuration = services.GetRequiredService<IConfiguration>();
    var connection = configuration.GetConnectionString("ProductDatabase")
        ?? throw new InvalidOperationException("Product database is not configured.");
    options.UseNpgsql(connection);
});

var modules = typeof(Program).Assembly.GetTypes()
    .Where(type => typeof(IGeneratedModule).IsAssignableFrom(type)
                   && type is { IsClass: true, IsAbstract: false })
    .OrderBy(type => type.FullName, StringComparer.Ordinal)
    .Select(type => (IGeneratedModule)Activator.CreateInstance(type)!)
    .ToArray();
foreach (var module in modules)
    module.RegisterServices(builder.Services);

var app = builder.Build();
app.UseExceptionHandler();
app.UseStatusCodePages(async statusContext =>
{
    await statusContext.HttpContext.Response.WriteAsJsonAsync(
        new ApiError("http_error", "The request could not be processed."));
});
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.MapGet("/health/ready", async (IServiceProvider services, CancellationToken ct) =>
{
    try
    {
        var db = services.GetRequiredService<ProductDbContext>();
        if (await db.Database.CanConnectAsync(ct))
            return Results.Ok(new { status = "ok" });
    }
    catch (Exception) when (!ct.IsCancellationRequested)
    {
        // A readiness response never exposes a connection string or database error.
    }
    return Results.Json(new ApiError("not_ready", "Product database is unavailable."),
                        statusCode: StatusCodes.Status503ServiceUnavailable);
});
foreach (var module in modules)
    module.MapEndpoints(app);

app.Run();
public partial class Program { }
