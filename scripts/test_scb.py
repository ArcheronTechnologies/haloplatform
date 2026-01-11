#!/usr/bin/env python3
"""Test SCB API - verify connection."""

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
        # Simple category query that worked before
        print("--- Simple category query (AB companies) ---")
        resp = await client.post(
            f"{base_url}/api/Je/HamtaForetag",
            json={
                "Kategorier": [
                    {"Kategori": "Juridisk form", "Kod": ["49"]}
                ],
                "MaxAntalRader": 5,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Got {len(data)} companies")
            for c in data[:3]:
                print(f"  {c.get('OrgNr')}: {c.get('Företagsnamn')}")
        else:
            print(f"Error: {resp.text}")

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(main())
