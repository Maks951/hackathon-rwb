using Generated.Api.Contracts;
using Microsoft.AspNetCore.Diagnostics;

namespace Generated.Api.Infrastructure;

public sealed class SafeExceptionHandler : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext context, Exception exception, CancellationToken cancellationToken)
    {
        var badInput = exception is BadHttpRequestException;
        context.Response.StatusCode = badInput ? StatusCodes.Status400BadRequest
                                              : StatusCodes.Status500InternalServerError;
        await context.Response.WriteAsJsonAsync(
            new ApiError(badInput ? "invalid_input" : "internal_error",
                         badInput ? "Invalid request." : "The request could not be processed."),
            cancellationToken);
        return true;
    }
}
