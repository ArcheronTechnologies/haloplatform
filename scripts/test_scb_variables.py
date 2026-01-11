#!/usr/bin/env python3
"""Explore SCB API filtering options to find 559xxx companies efficiently."""

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
        # First, get available variables
        print("=== Available Variables ===")
        resp = await client.get(
            f"{base_url}/api/Je/Variabler",
            headers={"Accept": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            variables = resp.json()
            for v in variables:
                print(f"  - {v.get('Namn', v)}")
                if isinstance(v, dict):
                    for key, val in v.items():
                        if key != 'Namn':
                            print(f"      {key}: {val}")
        else:
            print(f"Error: {resp.text}")

        print("\n=== Available Categories ===")
        await asyncio.sleep(1.5)  # Rate limiting
        resp = await client.get(
            f"{base_url}/api/Je/KategorierMedKodtabeller",
            headers={"Accept": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            categories = resp.json()
            for cat in categories:
                name = cat.get('Namn', cat) if isinstance(cat, dict) else cat
                print(f"  - {name}")
                # Show first few codes if available
                if isinstance(cat, dict) and 'Kodtabell' in cat:
                    codes = cat['Kodtabell'][:5]
                    for code in codes:
                        print(f"      {code.get('Kod')}: {code.get('Namn', code.get('Beskrivning', ''))}")
                    if len(cat['Kodtabell']) > 5:
                        print(f"      ... and {len(cat['Kodtabell']) - 5} more")
        else:
            print(f"Error: {resp.text}")

        # Try to find a way to filter by org number range
        # The "StarterMed" operator might work for prefix matching
        print("\n=== Test: Filter by org number prefix (559) using StarterMed ===")
        await asyncio.sleep(1.5)  # Rate limiting
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Variabler": [
                    {"Variabel": "OrgNr (10 siffror)", "Varde": "559", "Operator": "StarterMed"}
                ],
                "MaxAntalRader": 5,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Got {len(data)} companies")
            for c in data[:5]:
                print(f"  {c.get('OrgNr')}: {c.get('Företagsnamn')}")
        else:
            print(f"Error: {resp.text}")

        # Also try with 12-digit format (includes century prefix 16)
        print("\n=== Test: Filter by 12-digit org number prefix (16559) ===")
        await asyncio.sleep(1.5)
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Variabler": [
                    {"Variabel": "PeOrgNr", "Varde": "16559", "Operator": "StarterMed"}
                ],
                "MaxAntalRader": 5,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Got {len(data)} companies")
            for c in data[:5]:
                print(f"  {c.get('OrgNr')}: {c.get('Företagsnamn')}")
        else:
            print(f"Error: {resp.text}")

        # Try counting 559xxx companies
        print("\n=== Count: How many 559xxx companies exist? ===")
        await asyncio.sleep(1.5)
        resp = await client.post(
            f"{base_url}/api/Je/RaknaForetag",
            json={
                "Variabler": [
                    {"Variabel": "PeOrgNr", "Varde": "16559", "Operator": "StarterMed"}
                ],
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Count: {resp.json()}")
        else:
            print(f"Error: {resp.text}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(main())
