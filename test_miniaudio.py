import miniaudio, time
from miniaudio import FileFormat, SampleFormat, PlaybackDevice

client = miniaudio.IceCastClient("http://ice1.somafm.com/u80s-128-mp3")
print(f"Station: {client.station_name}")
print(f"Genre: {client.station_genre}")

stream = miniaudio.stream_any(
    client,
    source_format=FileFormat.MP3,
    output_format=SampleFormat.SIGNED16,
    nchannels=2,
    sample_rate=44100,
)

device = PlaybackDevice()
device.start(stream)
print("Playing for 5 seconds...")
time.sleep(5)
client._stop_stream = True
device.stop()
print("Done")
