#!/usr/bin/env python3
"""Test SCB API filtering for 559xxx companies using BorjarPa operator."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
import tempfile


async def main():
    cert_path = Path("./halo/secrets/scb_cert.p12")
    cert_password = "[REDACTED_PASSWORD]"

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

    base_url = "[REDACTED_API_ENDPOINT]"

    async with httpx.AsyncClient(cert=(str(cert_pem_path), str(key_pem_path)), timeout=120.0) as client:
        # The API docs say OrgNr (10 siffror) supports BorjarPa operator
        # Try filtering for 559xxx companies (newer companies, post-2018)

        print("=== Test: Count 559xxx companies ===")
        resp = await client.post(
            f"{base_url}/api/Je/RaknaForetag",
            json={
                "Variabler": [
                    {"Variabel": "OrgNr (10 siffror)", "Varde": "559", "Operator": "BorjarPa"}
                ],
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}  # Only Aktiebolag
                ],
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            count = resp.json()
            print(f"559xxx Aktiebolag count: {count}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)  # Rate limiting

        print("\n=== Test: Fetch 5 companies starting with 559 ===")
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Variabler": [
                    {"Variabel": "OrgNr (10 siffror)", "Varde": "559", "Operator": "BorjarPa"}
                ],
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}  # Only Aktiebolag
                ],
                "MaxAntalRader": 5,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Got {len(data)} companies")
            for c in data:
                print(f"  {c.get('OrgNr')}: {c.get('Företagsnamn')}")
                print(f"    Status: {c.get('Företagsstatus')}, Reg: {c.get('Registreringsstatus')}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)

        # Try with active companies only
        print("\n=== Test: Active 559xxx Aktiebolag ===")
        resp = await client.post(
            f"{base_url}/api/Je/RaknaForetag",
            json={
                "Variabler": [
                    {"Variabel": "OrgNr (10 siffror)", "Varde": "559", "Operator": "BorjarPa"}
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
            count = resp.json()
            print(f"Active 559xxx Aktiebolag count: {count}")
        else:
            print(f"Error: {resp.text}")

        await asyncio.sleep(1.5)

        # Fetch some active ones
        print("\n=== Test: Fetch 10 active 559xxx Aktiebolag ===")
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Variabler": [
                    {"Variabel": "OrgNr (10 siffror)", "Varde": "559", "Operator": "BorjarPa"}
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
