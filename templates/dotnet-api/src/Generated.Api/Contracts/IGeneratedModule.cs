namespace Generated.Api.Contracts;

// Each Qwen-generated domain module implements this interface and has a public
// parameterless constructor. Route handlers receive dependencies through DI.
public interface IGeneratedModule
{
    void RegisterServices(IServiceCollection services) { }
    void MapEndpoints(IEndpointRouteBuilder endpoints);
}
