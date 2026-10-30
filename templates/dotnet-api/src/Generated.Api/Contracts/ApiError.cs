namespace Generated.Api.Contracts;

public sealed record ApiError(string Code, string Message, object? Details = null);
