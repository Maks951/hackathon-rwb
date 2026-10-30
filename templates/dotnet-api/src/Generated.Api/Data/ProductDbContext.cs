using Microsoft.EntityFrameworkCore;

namespace Generated.Api.Data;

public partial class ProductDbContext(DbContextOptions<ProductDbContext> options) : DbContext(options)
{
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(ProductDbContext).Assembly);
        ConfigureGeneratedModel(modelBuilder);
    }

    partial void ConfigureGeneratedModel(ModelBuilder modelBuilder);
}
