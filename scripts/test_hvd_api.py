#!/usr/bin/env python3
"""Parse XBRL tags to extract directors from annual report."""

import httpx
import asyncio
import zipfile
import io
import os
import re
from xml.etree import ElementTree as ET

async def test_hvd():
    client_id = "[REDACTED_CLIENT_ID]"
    client_secret = "[REDACTED_CLIENT_SECRET]"
    scopes = "vardefulla-datamangder:ping vardefulla-datamangder:read"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Get token
        token_resp = await client.post(
            "[REDACTED_GOV_API]",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scopes,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        token = token_resp.json()["access_token"]

        # Download the report
        orgnr = "5592584386"
        doc_id = "7d484794-0055-4964-a026-825a1fb42e43_paket"

        print(f"Downloading document for {orgnr}...")
        dl_resp = await client.get(
            f"[REDACTED_GOV_API]",
            headers={"Authorization": f"Bearer {token}"}
        )

        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            xhtml_name = zf.namelist()[0]
            xhtml_content = zf.read(xhtml_name).decode('utf-8')

        # Look for specific XBRL tags related to signatures/directors
        print("\n" + "="*60)
        print("SEARCHING FOR XBRL SIGNATURE/DIRECTOR TAGS")
        print("="*60)

        # XBRL tags that might contain director info
        patterns = [
            # Signature/representative fields
            (r'UnderskriftFaststallelseintygForetradareForetradarroll.*?>([^<]+)<', "Role"),
            (r'UnderskriftFaststallelseintygForetradareForetradarnamn.*?>([^<]+)<', "Name"),
            (r'UnderskriftForetradareForetradarnamn.*?>([^<]+)<', "Name"),
            (r'UnderskriftForetradareForetradarroll.*?>([^<]+)<', "Role"),
            # Signature date
            (r'UnderskriftSignaturdatum.*?>([^<]+)<', "SignDate"),
            # General signature fields
            (r'Foretradarnamn.*?>([^<]+)<', "Name"),
            (r'Foretradarroll.*?>([^<]+)<', "Role"),
        ]

        for pattern, label in patterns:
            matches = re.findall(pattern, xhtml_content, re.IGNORECASE)
            if matches:
                print(f"\n{label}:")
                for m in matches[:10]:
                    clean = m.strip()
                    if clean and len(clean) > 1:
                        print(f"  {clean}")

        # Parse as XML to get structured data
        print("\n" + "="*60)
        print("PARSING XBRL ELEMENTS")
        print("="*60)

        # Define namespaces
        namespaces = {
            'ix': 'http://www.xbrl.org/2013/inlineXBRL',
            'xbrli': 'http://www.xbrl.org/2003/instance',
            'se-comp-base': 'http://www.bolagsverket.se/se/fr/comp-base/2020-12-01',
            'se-gen-base': 'http://www.taxonomier.se/se/fr/gen-base/2021-10-31',
        }

        # Parse XML
        try:
            root = ET.fromstring(xhtml_content.encode('utf-8'))

            # Find all ix:nonNumeric elements (text fields)
            for elem in root.iter():
                if 'nonNumeric' in elem.tag or 'nonFraction' in elem.tag:
                    name = elem.get('name', '')
                    text = ''.join(elem.itertext()).strip()

                    # Filter for signature/director related
                    if any(kw in name.lower() for kw in ['foretradar', 'underskrift', 'styrelse', 'firma']):
                        if text and len(text) > 1:
                            print(f"  {name}: {text}")

        except ET.ParseError as e:
            print(f"XML parse error: {e}")
            # Fall back to regex

        # Also search for the signature page section
        print("\n" + "="*60)
        print("SIGNATURE PAGE SECTION")
        print("="*60)

        # Look for the signature block
        sig_patterns = [
            r'Underskrifter.*?</table>',
            r'underteckna.*?</div>',
        ]

        for pattern in sig_patterns:
            matches = re.findall(pattern, xhtml_content, re.IGNORECASE | re.DOTALL)
            for m in matches[:1]:
                # Clean HTML
                clean = re.sub(r'<[^>]+>', '\n', m)
                clean = re.sub(r'\s+', ' ', clean).strip()
                print(clean[:500])

        # Simple approach: find name + role pairs
        print("\n" + "="*60)
        print("EXTRACTED DIRECTORS")
        print("="*60)

        # Pattern: Name, Role (where role contains styrelse/VD/etc)
        director_pattern = r'>([A-ZÅÄÖ][a-zåäöéè]+(?:\s+[A-ZÅÄÖ][a-zåäöéè]+){1,3})\s*,?\s*(Styrelse(?:ledamot|ns ordförande|suppleant)?|VD|Verkställande direktör)[^<]*<'

        directors = re.findall(director_pattern, xhtml_content, re.IGNORECASE)
        for name, role in directors:
            print(f"  {name}: {role}")

        if not directors:
            # Broader search
            print("\nNo directors found with pattern. Looking for any name+role pairs...")

            # Find all text content
            text_only = re.sub(r'<[^>]+>', '\n', xhtml_content)
            lines = [l.strip() for l in text_only.split('\n') if l.strip()]

            for i, line in enumerate(lines):
                if any(role in line.lower() for role in ['styrelseledamot', 'ordförande', 'vd ']):
                    context = lines[max(0,i-2):i+3]
                    print(f"\n  Found at line {i}:")
                    for c in context:
                        print(f"    {c[:80]}")


if __name__ == "__main__":
    asyncio.run(test_hvd())
