class ShoppingCart:
    def __init__(self):
        self.items = []

    def add_item(self, name, price, qty=1):
        if price < 0 or qty < 1:
            raise ValueError("Invalid price or quantity")
        self.items.append({"name": name, "price": price, "qty": qty})

    def total(self):
        amount = 0
        for item in self.items:
            amount += item["price"] * item["qty"]
        return amount

    def checkout(self):
        if not self.items:
            raise ValueError("Cart is empty")
        return self.total()
