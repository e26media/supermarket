import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as c:
        r = await c.post("http://127.0.0.1:8000/auth/login", data={"username": "admin", "password": "admin123"})
        token = r.json()["access_token"]
        r2 = await c.get("http://127.0.0.1:8000/products/", headers={"Authorization": f"Bearer {token}"})
        data = r2.json()
        print(f"Status: {r2.status_code}, Count: {len(data)}")
        if data:
            print(f"First product: {data[0]['name']}")
        else:
            print("No products returned from API")

asyncio.run(test())
