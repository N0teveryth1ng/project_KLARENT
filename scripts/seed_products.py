from app.database.session import SessionLocal
from demo_app.models.product import Product

db = SessionLocal()

products = [
    Product(name="Laptop", description="High performance laptop", price=999.99, stock=10),
    Product(name="Mouse", description="Wireless mouse", price=29.99, stock=50),
    Product(name="Keyboard", description="Mechanical keyboard", price=79.99, stock=30),
    Product(name="Monitor", description="24 inch monitor", price=299.99, stock=15),
]

for p in products:
    existing = db.query(Product).filter(Product.name == p.name).first()
    if not existing:
        db.add(p)

db.commit()
print("Products seeded")
db.close()
