#!/usr/bin/env python3
import os
import random
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

CHIP8_MEMORY_SIZE = 4096
CHIP8_START = 0x200
MAX_ROM = CHIP8_MEMORY_SIZE - CHIP8_START
MAX_STACK = 16
SCREEN_WIDTH = 64
SCREEN_HEIGHT = 32
PIXEL_SCALE = 12
CPU_HZ = 500
TIMER_HZ = 60

FONTSET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0,
    0x20, 0x60, 0x20, 0x20, 0x70,
    0xF0, 0x10, 0xF0, 0x80, 0xF0,
    0xF0, 0x10, 0xF0, 0x10, 0xF0,
    0x90, 0x90, 0xF0, 0x10, 0x10,
    0xF0, 0x80, 0xF0, 0x10, 0xF0,
    0xF0, 0x80, 0xF0, 0x90, 0xF0,
    0xF0, 0x10, 0x20, 0x40, 0x40,
    0xF0, 0x90, 0xF0, 0x90, 0xF0,
    0xF0, 0x90, 0xF0, 0x10, 0xF0,
    0xF0, 0x90, 0xF0, 0x90, 0x90,
    0xE0, 0x90, 0xE0, 0x90, 0xE0,
    0xF0, 0x80, 0x80, 0x80, 0xF0,
    0xE0, 0x90, 0x90, 0x90, 0xE0,
    0xF0, 0x80, 0xF0, 0x80, 0xF0,
    0xF0, 0x80, 0xF0, 0x80, 0x80,
]

# Built-in IBM logo ROM (runs with no external files)
DEFAULT_ROM = bytes.fromhex(
    "00e0a22a00e0a0a060006000a0001e00020a0a008aa0a6a2"
    "0e0000220a000608080600060406001070505078003844443c"
    "00fca4a4a4007ca2a27c003854545800fc242424000060a0"
    "a07e0000d600"
)

KEY_MAP = {
    "1": 0x1, "2": 0x2, "3": 0x3, "4": 0xC,
    "q": 0x4, "w": 0x5, "e": 0x6, "r": 0xD,
    "a": 0x7, "s": 0x8, "d": 0x9, "f": 0xE,
    "z": 0xA, "x": 0x0, "c": 0xB, "v": 0xF,
}


class Chip8:
    def __init__(self):
        self.reset()

    def reset(self):
        self.memory = [0] * CHIP8_MEMORY_SIZE
        self.V = [0] * 16
        self.I = 0
        self.pc = CHIP8_START
        self.stack: list[int] = []
        self.delay_timer = 0
        self.sound_timer = 0
        self.display = [0] * (SCREEN_WIDTH * SCREEN_HEIGHT)
        self.draw_flag = False
        self.keys = [0] * 16
        self.waiting_for_key = False
        self.wait_key_reg = 0
        for i, byte in enumerate(FONTSET):
            self.memory[i] = byte

    def load_rom_bytes(self, rom: bytes) -> bool:
        if not rom:
            return False
        self.reset()
        for i, byte in enumerate(rom[:MAX_ROM]):
            self.memory[CHIP8_START + i] = byte
        return True

    def load_rom_file(self, path: str) -> bool:
        try:
            with open(path, "rb") as f:
                return self.load_rom_bytes(f.read(MAX_ROM))
        except OSError as e:
            messagebox.showerror("ROM Error", f"Could not load ROM:\n{e}")
            return False

    def cycle(self):
        if self.waiting_for_key:
            for k in range(16):
                if self.keys[k]:
                    self.V[self.wait_key_reg] = k
                    self.waiting_for_key = False
                    return
            return

        if self.pc + 1 >= CHIP8_MEMORY_SIZE:
            return

        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc += 2

        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        n = opcode & 0x000F
        nn = opcode & 0x00FF
        nnn = opcode & 0x0FFF

        if opcode == 0x00E0:
            self.display = [0] * (SCREEN_WIDTH * SCREEN_HEIGHT)
            self.draw_flag = True
        elif opcode == 0x00EE:
            if self.stack:
                self.pc = self.stack.pop()
        elif (opcode & 0xF000) == 0x1000:
            self.pc = nnn
        elif (opcode & 0xF000) == 0x2000:
            if len(self.stack) < MAX_STACK:
                self.stack.append(self.pc)
                self.pc = nnn
        elif (opcode & 0xF000) == 0x3000:
            if self.V[x] == nn:
                self.pc += 2
        elif (opcode & 0xF000) == 0x4000:
            if self.V[x] != nn:
                self.pc += 2
        elif (opcode & 0xF000) == 0x5000 and n == 0:
            if self.V[x] == self.V[y]:
                self.pc += 2
        elif (opcode & 0xF000) == 0x6000:
            self.V[x] = nn
        elif (opcode & 0xF000) == 0x7000:
            self.V[x] = (self.V[x] + nn) & 0xFF
        elif (opcode & 0xF000) == 0x8000:
            if n == 0:
                self.V[x] = self.V[y]
            elif n == 1:
                self.V[x] |= self.V[y]
            elif n == 2:
                self.V[x] &= self.V[y]
            elif n == 3:
                self.V[x] ^= self.V[y]
            elif n == 4:
                total = self.V[x] + self.V[y]
                self.V[0xF] = 1 if total > 0xFF else 0
                self.V[x] = total & 0xFF
            elif n == 5:
                self.V[0xF] = 1 if self.V[x] >= self.V[y] else 0
                self.V[x] = (self.V[x] - self.V[y]) & 0xFF
            elif n == 6:
                self.V[0xF] = self.V[x] & 1
                self.V[x] >>= 1
            elif n == 7:
                self.V[0xF] = 1 if self.V[y] >= self.V[x] else 0
                self.V[x] = (self.V[y] - self.V[x]) & 0xFF
            elif n == 0xE:
                self.V[0xF] = (self.V[x] >> 7) & 1
                self.V[x] = (self.V[x] << 1) & 0xFF
        elif (opcode & 0xF000) == 0x9000 and n == 0:
            if self.V[x] != self.V[y]:
                self.pc += 2
        elif (opcode & 0xF000) == 0xA000:
            self.I = nnn
        elif (opcode & 0xF000) == 0xB000:
            self.pc = nnn + self.V[0]
        elif (opcode & 0xF000) == 0xC000:
            self.V[x] = random.randint(0, 255) & nn
        elif (opcode & 0xF000) == 0xD000:
            self.V[0xF] = 0
            px = self.V[x] % SCREEN_WIDTH
            py = self.V[y] % SCREEN_HEIGHT
            for row in range(n):
                sprite_byte = self.memory[self.I + row]
                for col in range(8):
                    if sprite_byte & (0x80 >> col):
                        cx = (px + col) % SCREEN_WIDTH
                        cy = (py + row) % SCREEN_HEIGHT
                        idx = cy * SCREEN_WIDTH + cx
                        if self.display[idx]:
                            self.V[0xF] = 1
                        self.display[idx] ^= 1
            self.draw_flag = True
        elif (opcode & 0xF000) == 0xE000:
            key = self.V[x] & 0xF
            if nn == 0x9E:
                if self.keys[key]:
                    self.pc += 2
            elif nn == 0xA1:
                if not self.keys[key]:
                    self.pc += 2
        elif (opcode & 0xF000) == 0xF000:
            if nn == 0x07:
                self.V[x] = self.delay_timer
            elif nn == 0x0A:
                for k in range(16):
                    if self.keys[k]:
                        self.V[x] = k
                        break
                else:
                    self.waiting_for_key = True
                    self.wait_key_reg = x
                    self.pc -= 2
            elif nn == 0x15:
                self.delay_timer = self.V[x]
            elif nn == 0x18:
                self.sound_timer = self.V[x]
            elif nn == 0x1E:
                self.I = (self.I + self.V[x]) & 0xFFF
            elif nn == 0x29:
                self.I = (self.V[x] & 0xF) * 5
            elif nn == 0x33:
                val = self.V[x]
                self.memory[self.I] = val // 100
                self.memory[self.I + 1] = (val // 10) % 10
                self.memory[self.I + 2] = val % 10
            elif nn == 0x55:
                for i in range(x + 1):
                    self.memory[self.I + i] = self.V[i]
            elif nn == 0x65:
                for i in range(x + 1):
                    self.V[i] = self.memory[self.I + i]

    def update_timers(self):
        if self.delay_timer > 0:
            self.delay_timer -= 1
        if self.sound_timer > 0:
            self.sound_timer -= 1

    def key_pressed(self, key: str):
        k = KEY_MAP.get(key.lower())
        if k is None:
            return
        self.keys[k] = 1
        if self.waiting_for_key:
            self.V[self.wait_key_reg] = k
            self.waiting_for_key = False

    def key_released(self, key: str):
        k = KEY_MAP.get(key.lower())
        if k is not None:
            self.keys[k] = 0


class EmulatorApp:
    def __init__(self, root: tk.Tk, rom_bytes: bytes, rom_label: str):
        self.root = root
        self.rom_bytes = rom_bytes
        self.rom_label = rom_label
        self.emu = Chip8()
        self.emu.load_rom_bytes(rom_bytes)
        self.running = True
        self.cpu_accum = 0.0
        self.timer_accum = 0.0

        root.title("AC HOLDINGS Chip-8 emu 0.1")
        root.configure(bg="black")
        root.resizable(False, False)

        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open ROM...", command=self.open_rom)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.close)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)

        self.canvas = tk.Canvas(
            root,
            width=SCREEN_WIDTH * PIXEL_SCALE,
            height=SCREEN_HEIGHT * PIXEL_SCALE,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack(padx=8, pady=8)

        status = tk.Label(
            root,
            text=f"ROM: {rom_label}",
            bg="black",
            fg="#4488ff",
            font=("Segoe UI", 9),
        )
        status.pack(pady=(0, 4))

        btn_frame = tk.Frame(root, bg="black")
        btn_frame.pack(pady=(0, 8))

        tk.Button(
            btn_frame,
            text="Reset",
            bg="black",
            fg="#4488ff",
            activebackground="#222222",
            activeforeground="#6666ff",
            relief=tk.FLAT,
            padx=16,
            pady=4,
            font=("Segoe UI", 9),
            command=self.reset,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_frame,
            text="Close",
            bg="black",
            fg="#4488ff",
            activebackground="#222222",
            activeforeground="#6666ff",
            relief=tk.FLAT,
            padx=16,
            pady=4,
            font=("Segoe UI", 9),
            command=self.close,
        ).pack(side=tk.LEFT, padx=4)

        for key in KEY_MAP:
            root.bind(f"<KeyPress-{key}>", self.on_key_down)
            root.bind(f"<KeyRelease-{key}>", self.on_key_up)
            if key.isalpha():
                root.bind(f"<KeyPress-{key.upper()}>", self.on_key_down)
                root.bind(f"<KeyRelease-{key.upper()}>", self.on_key_up)

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.focus_set()

        self.last_tick = time.perf_counter()
        self.render()
        self.tick()

    def open_rom(self):
        path = filedialog.askopenfilename(
            title="Open CHIP-8 ROM",
            filetypes=[("CHIP-8 ROM", "*.ch8 *.rom"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read(MAX_ROM)
        if self.emu.load_rom_bytes(data):
            self.rom_bytes = data
            self.rom_label = os.path.basename(path)
            self.cpu_accum = 0.0
            self.timer_accum = 0.0
            self.render()

    def reset(self):
        self.emu.load_rom_bytes(self.rom_bytes)
        self.cpu_accum = 0.0
        self.timer_accum = 0.0
        self.render()

    def close(self):
        self.running = False
        self.root.destroy()

    def on_key_down(self, e):
        self.emu.key_pressed(e.keysym)

    def on_key_up(self, e):
        self.emu.key_released(e.keysym)

    def tick(self):
        if not self.running:
            return

        now = time.perf_counter()
        dt = min(now - self.last_tick, 0.05)
        self.last_tick = now

        self.cpu_accum += dt
        step = 1.0 / CPU_HZ
        while self.cpu_accum >= step:
            self.emu.cycle()
            self.cpu_accum -= step

        self.timer_accum += dt
        tick = 1.0 / TIMER_HZ
        while self.timer_accum >= tick:
            self.emu.update_timers()
            self.timer_accum -= tick

        if self.emu.draw_flag:
            self.render()
            self.emu.draw_flag = False

        self.root.after(16, self.tick)

    def render(self):
        self.canvas.delete("all")
        for y in range(SCREEN_HEIGHT):
            for x in range(SCREEN_WIDTH):
                if self.emu.display[y * SCREEN_WIDTH + x]:
                    sx = x * PIXEL_SCALE
                    sy = y * PIXEL_SCALE
                    self.canvas.create_rectangle(
                        sx,
                        sy,
                        sx + PIXEL_SCALE,
                        sy + PIXEL_SCALE,
                        fill="#0044ff",
                        outline="",
                    )


def main():
    rom_bytes = DEFAULT_ROM
    rom_label = "IBM Logo (built-in)"

    if len(sys.argv) >= 2:
        path = os.path.abspath(sys.argv[1])
        try:
            with open(path, "rb") as f:
                rom_bytes = f.read(MAX_ROM)
            rom_label = os.path.basename(path)
        except OSError as e:
            messagebox.showerror("ROM Error", f"Could not load ROM:\n{e}\nUsing built-in demo.")
            rom_bytes = DEFAULT_ROM
            rom_label = "IBM Logo (built-in)"

    root = tk.Tk()
    EmulatorApp(root, rom_bytes, rom_label)
    root.mainloop()


if __name__ == "__main__":
    main()
