#!/usr/bin/env python3
"""List module metadata and imports from a decrypted big-endian PS3 PRX."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


PT_LOAD = 1


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from(">Q", data, offset)[0]


class Prx:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        if self.data[:4] != b"\x7fELF" or self.data[4:7] != b"\x02\x02\x01":
            raise ValueError("expected a 64-bit big-endian ELF")

        phoff = u64(self.data, 0x20)
        phentsize = u16(self.data, 0x36)
        phnum = u16(self.data, 0x38)
        self.loads: list[tuple[int, int, int, int, int]] = []
        self.module_info_offset: int | None = None

        for index in range(phnum):
            offset = phoff + index * phentsize
            p_type = u32(self.data, offset)
            p_offset = u64(self.data, offset + 0x08)
            p_vaddr = u64(self.data, offset + 0x10)
            p_paddr = u64(self.data, offset + 0x18)
            p_filesz = u64(self.data, offset + 0x20)
            p_flags = u32(self.data, offset + 0x30)
            if p_type == PT_LOAD:
                self.loads.append((p_vaddr, p_offset, p_filesz, p_flags, p_paddr))
                if self.module_info_offset is None and p_paddr:
                    # Sony PRX files use p_paddr of the first LOAD entry as
                    # the file offset of sys_prx_module_info.
                    self.module_info_offset = p_paddr

        if self.module_info_offset is None:
            raise ValueError("PRX module-info offset was not found")

    def file_offset(self, vaddr: int) -> int:
        for start, file_offset, size, _flags, _paddr in self.loads:
            if start <= vaddr < start + size:
                return file_offset + (vaddr - start)
        raise ValueError(f"virtual address 0x{vaddr:08x} is outside file-backed LOAD data")

    def cstring(self, vaddr: int) -> str:
        offset = self.file_offset(vaddr)
        end = self.data.find(b"\0", offset)
        if end < 0:
            raise ValueError(f"unterminated string at 0x{vaddr:08x}")
        return self.data[offset:end].decode("ascii", errors="replace")

    def words(self, vaddr: int, count: int) -> list[int]:
        offset = self.file_offset(vaddr)
        return list(struct.unpack_from(f">{count}I", self.data, offset))

    def describe(self) -> None:
        info = self.module_info_offset
        assert info is not None
        attributes = u16(self.data, info)
        version = u16(self.data, info + 2)
        raw_name = self.data[info + 4 : info + 32]
        name = raw_name.split(b"\0", 1)[0].decode("ascii", errors="replace")
        toc, exports_start, exports_end, imports_start, imports_end = struct.unpack_from(
            ">5I", self.data, info + 32
        )

        print(f"file: {self.path}")
        print(f"module: {name}")
        print(f"attributes: 0x{attributes:04x}")
        print(f"version: 0x{version:04x}")
        print(f"toc: 0x{toc:08x}")
        print(f"exports: 0x{exports_start:08x}..0x{exports_end:08x}")
        print(f"imports: 0x{imports_start:08x}..0x{imports_end:08x}")
        print()

        cursor = imports_start
        while cursor < imports_end:
            offset = self.file_offset(cursor)
            size = self.data[offset]
            if size < 0x1C or cursor + size > imports_end:
                raise ValueError(f"invalid import record size 0x{size:x} at 0x{cursor:08x}")

            version_i = u16(self.data, offset + 2)
            attributes_i = u16(self.data, offset + 4)
            function_count = u16(self.data, offset + 6)
            variable_count = u16(self.data, offset + 8)
            tls_count = u16(self.data, offset + 10)
            name_ptr = u32(self.data, offset + 16)
            fnid_ptr = u32(self.data, offset + 20)
            fstub_ptr = u32(self.data, offset + 24)
            module_name = self.cstring(name_ptr)

            print(
                f"[{module_name}] record=0x{cursor:08x} size=0x{size:02x} "
                f"version=0x{version_i:04x} attributes=0x{attributes_i:04x} "
                f"functions={function_count} variables={variable_count} tls={tls_count}"
            )
            if function_count:
                nids = self.words(fnid_ptr, function_count)
                stubs = self.words(fstub_ptr, function_count)
                for index, (nid, stub) in enumerate(zip(nids, stubs)):
                    print(f"  {index:3d} nid=0x{nid:08x} stub=0x{stub:08x}")
            print()
            cursor += size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    for index, path in enumerate(args.files):
        if index:
            print("=" * 72)
        Prx(path).describe()


if __name__ == "__main__":
    main()
