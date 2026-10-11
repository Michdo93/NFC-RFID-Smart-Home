"""
ndef.py – NFC Data Exchange Format (Kapitel 3 und 7).

Eine NDEF-Nachricht besteht aus Datensätzen (Records). Jeder Record hat einen Kopf mit
Flags und TNF (Type Name Format), einen Typ und Nutzdaten:

  Byte 0: MB | ME | CF | SR | IL | TNF(3 Bit)
          MB/ME = erster/letzter Record, SR = kurzer Record (Länge 1 Byte), IL = mit ID
  Byte 1: Länge des Typs
  Byte 2: Länge der Nutzdaten (SR: 1 Byte, sonst 4 Byte)
  [ID-Länge] Typ [ID] Nutzdaten

Auf einem NTAG steht die Nachricht in einem TLV-Block: 03 <Länge> <Nachricht> FE.

Dieses Modul kommt ohne fremde Bibliothek aus – so ist sichtbar, was auf dem Tag steht.
Für größere Projekte gibt es ndeflib (pip install ndeflib).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

TNF_EMPTY, TNF_WELL_KNOWN, TNF_MEDIA, TNF_URI, TNF_EXTERNAL = 0, 1, 2, 3, 4

# URI-Präfixe (NFC Forum URI RTD): ein Byte ersetzt den Anfang der Adresse
URI_PREFIXES = [
    "", "http://www.", "https://www.", "http://", "https://", "tel:", "mailto:",
    "ftp://anonymous:anonymous@", "ftp://ftp.", "ftps://", "sftp://", "smb://", "nfs://",
    "ftp://", "dav://", "news:", "telnet://", "imap:", "rtsp://", "urn:", "pop:", "sip:",
    "sips:", "tftp:", "btspp://", "btl2cap://", "btgoep://", "tcpobex://", "irdaobex://",
    "file://", "urn:epc:id:", "urn:epc:tag:", "urn:epc:pat:", "urn:epc:raw:", "urn:epc:",
    "urn:nfc:",
]


@dataclass
class Record:
    tnf: int
    type: bytes
    payload: bytes
    id: bytes = b""

    # -- bequeme Konstruktoren ----------------------------------------------------------
    @staticmethod
    def uri(uri: str) -> "Record":
        code, rest = 0, uri
        for i, p in enumerate(URI_PREFIXES):
            if i and uri.startswith(p) and len(p) > len(URI_PREFIXES[code]):
                code, rest = i, uri[len(p):]
        return Record(TNF_WELL_KNOWN, b"U", bytes([code]) + rest.encode("utf-8"))

    @staticmethod
    def text(text: str, lang: str = "de") -> "Record":
        lb = lang.encode("ascii")
        return Record(TNF_WELL_KNOWN, b"T", bytes([len(lb)]) + lb + text.encode("utf-8"))

    @staticmethod
    def external(type_name: str, payload: bytes) -> "Record":
        """NFC-Forum External Type, z. B. 'home.arpa:nfh' (Domain:Typ, klein geschrieben)."""
        return Record(TNF_EXTERNAL, type_name.lower().encode("ascii"), payload)

    @staticmethod
    def mime(mime_type: str, payload: bytes) -> "Record":
        return Record(TNF_MEDIA, mime_type.encode("ascii"), payload)

    # -- Auswertung ----------------------------------------------------------------------
    @property
    def type_name(self) -> str:
        return self.type.decode("ascii", "replace")

    def as_uri(self) -> Optional[str]:
        if self.tnf == TNF_WELL_KNOWN and self.type == b"U" and self.payload:
            code = self.payload[0]
            prefix = URI_PREFIXES[code] if code < len(URI_PREFIXES) else ""
            return prefix + self.payload[1:].decode("utf-8", "replace")
        return None

    def as_text(self) -> Optional[str]:
        if self.tnf == TNF_WELL_KNOWN and self.type == b"T" and self.payload:
            status = self.payload[0]
            lang_len = status & 0x3F
            enc = "utf-16" if status & 0x80 else "utf-8"
            return self.payload[1 + lang_len:].decode(enc, "replace")
        return None

    def describe(self) -> str:
        if self.as_uri() is not None:
            return f"URI   {self.as_uri()}"
        if self.as_text() is not None:
            return f"Text  {self.as_text()}"
        kind = {TNF_EXTERNAL: "Ext. ", TNF_MEDIA: "MIME "}.get(self.tnf, f"TNF{self.tnf} ")
        return f"{kind} {self.type_name} ({len(self.payload)} Byte)"


def encode_message(records: List[Record]) -> bytes:
    out = bytearray()
    for i, r in enumerate(records):
        sr = len(r.payload) < 256
        flags = r.tnf & 0x07
        flags |= 0x80 if i == 0 else 0
        flags |= 0x40 if i == len(records) - 1 else 0
        flags |= 0x10 if sr else 0
        flags |= 0x08 if r.id else 0
        out.append(flags)
        out.append(len(r.type))
        out += bytes([len(r.payload)]) if sr else len(r.payload).to_bytes(4, "big")
        if r.id:
            out.append(len(r.id))
        out += r.type + r.id + r.payload
    return bytes(out)


def decode_message(data: bytes) -> List[Record]:
    records, pos = [], 0
    while pos < len(data):
        flags = data[pos]
        type_len = data[pos + 1]
        pos += 2
        if flags & 0x10:
            plen = data[pos]
            pos += 1
        else:
            plen = int.from_bytes(data[pos:pos + 4], "big")
            pos += 4
        id_len = 0
        if flags & 0x08:
            id_len = data[pos]
            pos += 1
        rtype = data[pos:pos + type_len]
        pos += type_len
        rid = data[pos:pos + id_len]
        pos += id_len
        payload = data[pos:pos + plen]
        if len(payload) != plen:
            raise ValueError("NDEF-Nachricht abgeschnitten")
        pos += plen
        records.append(Record(flags & 0x07, bytes(rtype), bytes(payload), bytes(rid)))
        if flags & 0x40:                         # ME: letzter Record
            break
    return records


# -- TLV (Type-Length-Value) auf NFC-Forum-Typ-2-Tags (NTAG) -------------------------------
def wrap_tlv(message: bytes) -> bytes:
    n = len(message)
    length = bytes([n]) if n < 0xFF else bytes([0xFF]) + n.to_bytes(2, "big")
    return bytes([0x03]) + length + message + bytes([0xFE])


def find_ndef_tlv(memory: bytes) -> Optional[bytes]:
    """Den NDEF-Block (Typ 03) im Nutzspeicher finden. None, wenn keiner da ist."""
    pos = 0
    while pos < len(memory):
        t = memory[pos]
        if t == 0x00:                            # NULL-TLV: Füllbyte
            pos += 1
            continue
        if t == 0xFE:                            # Terminator
            return None
        if pos + 1 >= len(memory):
            return None
        n = memory[pos + 1]
        hdr = 2
        if n == 0xFF:
            n = int.from_bytes(memory[pos + 2:pos + 4], "big")
            hdr = 4
        if t == 0x03:
            value = memory[pos + hdr:pos + hdr + n]
            return value if len(value) == n else None
        pos += hdr + n                           # Lock-/Memory-Control-TLV überspringen
    return None
