CELL_SDK ?= /opt/cell
CELL_HOST_PATH ?= $(CELL_SDK)/host-win32
CELL_TARGET_PATH ?= $(CELL_SDK)/target/ppu
WINE ?= wine
CC := $(WINE) $(CELL_HOST_PATH)/ppu/bin/ppu-lv2-gcc.exe
OBJDUMP := $(WINE) $(CELL_HOST_PATH)/ppu/bin/ppu-lv2-objdump.exe
FSELF := $(WINE) $(CELL_HOST_PATH)/bin/make_fself.exe

TARGET := disc_rgb_fix
C_SOURCES := source/disc_rgb_fix.c
ASM_SOURCES := source/rgbfix_hook.S
OBJECTS := $(C_SOURCES:.c=.o) $(ASM_SOURCES:.S=.o)

CFLAGS := -O2 -Wall -Wextra -std=gnu99
CFLAGS += -fno-exceptions -fno-builtin-printf
CFLAGS += -I$(CELL_TARGET_PATH)/include

LDFLAGS := -mprx-with-runtime
LDFLAGS += -L$(CELL_TARGET_PATH)/lib
# lib/libvshtask_export_stub.a is webMAN MOD's lib/ file; build-docker.sh fetches it.
LDFLAGS += -Llib
LDLIBS := -lfs_stub -llv2_stub -lvshtask_export_stub -lc

.PHONY: all clean disasm

all: $(TARGET).sprx disasm

source/%.o: source/%.c
	$(CC) $(CFLAGS) -c $< -o $@

source/%.o: source/%.S
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET).prx: $(OBJECTS)
	$(CC) $(CFLAGS) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(TARGET).sprx: $(TARGET).prx
	$(FSELF) $< $@

disasm: source/rgbfix_hook.o
	mkdir -p build
	$(OBJDUMP) -d source/rgbfix_hook.o > build/rgbfix_hook.disasm.txt

clean:
	rm -f $(OBJECTS) $(TARGET).prx $(TARGET).sprx build/rgbfix_hook.disasm.txt
