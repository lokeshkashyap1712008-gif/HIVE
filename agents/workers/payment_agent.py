"""HIVE — Payment Agent Worker (stub)"""
async def run(description: str, context: dict = None) -> dict:
    return {"status": "stub", "agent": "payment_agent", "description": description[:100], "tip": "Configure STRIPE_API_KEY for real payments"}