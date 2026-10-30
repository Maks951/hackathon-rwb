# Generated .NET backend skeleton

.NET 10 / C# 14, EF Core PostgreSQL provider. Domain code is supplied by Qwen;
this template deliberately contains no parking or ticketing business logic.

```bash
dotnet restore Generated.slnx --locked-mode
dotnet test Generated.slnx --no-restore
dotnet run --project src/Generated.Api
```

The product uses its own database. Configure `ConnectionStrings__ProductDatabase`
through the environment. `/health` is liveness; `/health/ready` checks that database.
The product does not call the Python platform to implement its domain.

Generation extension points (paths relative to the product root):

- `backend/src/Generated.Api/Generated/**/*.cs`: entities, EF configurations,
  services and endpoint modules implementing `Generated.Api.Contracts.IGeneratedModule`.
- `backend/tests/Generated.Api.Tests/Generated/**/*.cs`: generated acceptance tests.
- `ProductDbContext` is partial; generated code can implement `ConfigureGeneratedModel`
  or use `IEntityTypeConfiguration<T>` and `db.Set<T>()`.

Dependency manifests, host setup and lock files are fixed; model outputs cannot modify
them. Use exactly the endpoint paths from the shared `generated-api.json`. Tests and
frontend must consume the same contract. Adding a package requires a reviewed
template change, not an LLM patch. Runner isolation, SQL/PostGIS templates, product
Compose/CI and publication are integrated from the respective component owners.

References: [ASP.NET integration testing](https://learn.microsoft.com/en-us/aspnet/core/test/integration-tests?view=aspnetcore-10.0),
[Npgsql releases](https://github.com/npgsql/efcore.pg/releases).
