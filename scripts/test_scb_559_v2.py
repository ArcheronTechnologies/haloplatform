#!/usr/bin/env python3
"""Test SCB API filtering - trying different variable names and formats."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
import tempfile


async def main():
    cert_path = Path("./halo/secrets/scb_cert.p12")
    cert_password = "uyMBu2LtKfiY"

    # Extract PEM from PFX
    with open(cert_path, 'rb') as f:
        pfx_data = f.read()

    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        pfx_data,
        cert_password.encode()
    )

    temp_dir = tempfile.mkdtemp()
    cert_pem_path = Path(temp_dir) / "cert.pem"
    key_pem_path = Path(temp_dir) / "key.pem"

    with open(cert_pem_path, 'wb') as f:
        f.write(certificate.public_bytes(Encoding.PEM))

    with open(key_pem_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption()
        ))

    base_url = "https://privateapi.scb.se/nv0101/v1/sokpavar"

    async with httpx.AsyncClient(cert=(str(cert_pem_path), str(key_pem_path)), timeout=120.0) as client:
        # The API shows:
        # - Id_Variabel_JE: 'OrgNr (12 siffror)' supports BorjarPa
        # - Id_Variabel_JE: 'OrgNr (10 siffror)' supports BorjarPa
        # Let's try the 12-digit version since 559 is 3 digits

        # Try 12-digit format (16559 prefix for companies registered after 2000)
        print("=== Test 1: 12-digit org number with prefix 16559 ===")
        resp = await client.post(
            f"{base_url}/api/Je/RaknaForetag",
            json={
                "Variabler": [
                    {"Variabel": "OrgNr (12 siffror)", "Varde": "16559", "Operator": "BorjarPa"}
                ],
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Count: {resp.json()}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)

        # Try using Registreringsdatum instead - filter by registration date
        # 559xxx numbers were assigned starting around 2016
        print("\n=== Test 2: Filter by registration date (2019+) ===")
        resp = await client.post(
            f"{base_url}/api/Je/RaknaForetag",
            json={
                "Variabler": [
                    {"Variabel": "Registreringsdatum", "Varde": "20190101", "Operator": "FranOchMed"}
                ],
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}
                ],
                "Företagsstatus": "1",
                "Registreringsstatus": "1",
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Count: {resp.json()}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)

        # Fetch some
        print("\n=== Test 3: Fetch 10 companies registered after 2019 ===")
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Variabler": [
                    {"Variabel": "Registreringsdatum", "Varde": "20190101", "Operator": "FranOchMed"}
                ],
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}
                ],
                "Företagsstatus": "1",
                "Registreringsstatus": "1",
                "MaxAntalRader": 10,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Got {len(data)} companies")
            for c in data:
                print(f"  {c.get('OrgNr')}: {c.get('Företagsnamn')}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)

        # Now try with registered recently - 2023 onwards
        print("\n=== Test 4: Companies registered in 2023+ ===")
        resp = await client.post(
            f"{base_url}/api/Je/RaknaForetag",
            json={
                "Variabler": [
                    {"Variabel": "Registreringsdatum", "Varde": "20230101", "Operator": "FranOchMed"}
                ],
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}
                ],
                "Företagsstatus": "1",
                "Registreringsstatus": "1",
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Count: {resp.json()}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)

        # Fetch 2023+ companies
        print("\n=== Test 5: Fetch 10 companies registered 2023+ ===")
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Variabler": [
                    {"Variabel": "Registreringsdatum", "Varde": "20230101", "Operator": "FranOchMed"}
                ],
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}
                ],
                "Företagsstatus": "1",
                "Registreringsstatus": "1",
                "MaxAntalRader": 10,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Got {len(data)} companies")
            for c in data:
                print(f"  {c.get('OrgNr')}: {c.get('Företagsnamn')}")
        else:
            print(f"Error: {resp.text}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(main())
