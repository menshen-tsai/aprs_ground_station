import sys
import wave
import struct
import math
import numpy as np
import sounddevice as sd

class APRSEncoder:
    def __init__(self, source="N0CALL", dest="APRS", path=["WIDE1-1"], sample_rate=44100):
        self.sample_rate = sample_rate
        self.source = source.upper()
        self.dest = dest.upper()
        self.path = [p.upper() for p in path]
        self.phase = 0.0

    def _get_ax25_frame(self, info):
        def encode_call(call):
            call = call.split('-')
            name = call[0].ljust(6)[:6]
            ssid = int(call[1]) if len(call) > 1 else 0
            # Shift bits left by 1 for AX.25 address format
            addr = bytes([(ord(c) << 1) for c in name])
            addr += bytes([(0x60 | (ssid << 1))])
            return addr

        # Build address field
        dest_addr = encode_call(self.dest)
        src_addr = encode_call(self.source)
        path_addr = b"".join([encode_call(p) for p in self.path])
        
        full_header = bytearray(dest_addr + src_addr + path_addr)
        full_header[-1] |= 0x01 # Set Last Address Bit
        
        # Control: 0x03 (UI frame), PID: 0xf0 (no layer 3)
        msg = full_header + b"\x03\xf0" + info.encode('ascii')
        
        # CRC-16 CCITT
        crc = 0xFFFF
        for byte in msg:
            for i in range(8):
                if (crc ^ (byte >> i)) & 0x01:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1
        crc ^= 0xFFFF
        return msg + struct.pack('<H', crc)

    def _bits_to_audio(self, frame_bits, filename):
        # 1200 baud = 1200 Hz (Mark) and 2200 Hz (Space)
        baud_rate = 1200
        samples_per_bit = self.sample_rate / baud_rate
        amplitude = 16000 # ~50% volume to prevent clipping
        
        with wave.open(filename, 'wb') as f:
            f.setparams((1, 2, self.sample_rate, 0, 'NONE', 'not compressed'))
            
            current_state = True # True = 1200Hz, False = 2200Hz
            for bit in frame_bits:
                # NRZI: 0 causes a transition, 1 maintains current freq
                if bit == 0:
                    current_state = not current_state
                
                freq = 1200 if current_state else 2200
                
                for _ in range(int(samples_per_bit)):
                    self.phase += (2 * math.pi * freq) / self.sample_rate
                    sample = int(math.sin(self.phase) * amplitude)
                    f.writeframesraw(struct.pack('<h', sample))
                self.phase %= (2 * math.pi)

    def generate(self, data_str, filename="aprs_output.wav"):
        raw_frame = self._get_ax25_frame(data_str)
        
        # Bit stuffing: Add a 0 after five consecutive 1s
        bits = []
        ones = 0
        for byte in raw_frame:
            for i in range(8):
                bit = (byte >> i) & 0x01
                bits.append(bit)
                if bit == 1:
                    ones += 1
                    if ones == 5:
                        bits.append(0)
                        ones = 0
                else:
                    ones = 0
                    
        # Add Flags (01111110) for preamble/postamble
        flag = [0, 1, 1, 1, 1, 1, 1, 0]
        final_bits = (flag * 50) + bits + (flag * 5)
        
        self._bits_to_audio(final_bits, filename)
        print(f"Generated {filename} with content: {data_str}")

def play_wave(filename): 
    with wave.open(filename, 'rb') as wf: 
        sample_rate = wf.getframerate() 
        frames = wf.readframes(wf.getnframes()) 
        # Convert byte data to numpy array 
        audio = np.frombuffer(frames, dtype=np.int16) 
        sd.play(audio, samplerate=sample_rate) 
        sd.wait()
            


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aprs.py <APRS Command>")
        sys.exit(1)
    aprs_command = sys.argv[1]    
    # --- RUN SCRIPT ---
    encoder = APRSEncoder(source="N0CALL", dest="APCSS")
    # APRS status message format usually starts with '>'
    filename = aprs_command+"_aprs.wav"
    new_filename = filename.replace("=", "_")
    encoder.generate(">"+aprs_command, new_filename)
    play_wave(new_filename)
