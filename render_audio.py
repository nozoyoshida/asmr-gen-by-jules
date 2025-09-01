import sys
import json
import numpy as np
import soundfile as sf
import scipy.signal
from pysofaconventions import SOFAFile
from pedalboard import Pedalboard, Reverb
from scipy.spatial.transform import Rotation

# --- Constants ---
TARGET_SAMPLE_RATE = 44100
OUTPUT_FILENAME = "output.wav"
REFERENCE_DISTANCE = 1.0
MIN_DISTANCE = 0.2
HRTF_FILENAME = 'hrtf.sofa'
BLOCK_SIZE = 512 # For convolution processing

def load_audio(filepath):
    """Loads and preprocesses the audio file."""
    try:
        data, samplerate = sf.read(filepath, dtype='float64')
        print(f"Loaded audio file '{filepath}' with sample rate {samplerate}.")
    except FileNotFoundError:
        print(f"Error: Audio file not found at '{filepath}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading audio file: {e}")
        sys.exit(1)

    if data.ndim > 1:
        print("Audio is not mono. Converting to mono by averaging channels.")
        data = np.mean(data, axis=1)

    if samplerate != TARGET_SAMPLE_RATE:
        print(f"Resampling from {samplerate} Hz to {TARGET_SAMPLE_RATE} Hz.")
        num_samples = int(len(data) * TARGET_SAMPLE_RATE / samplerate)
        data = scipy.signal.resample(data, num_samples)

    return data, TARGET_SAMPLE_RATE

def load_plan(filepath):
    """Loads the JSON panning plan."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Plan file not found at '{filepath}'")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{filepath}'.")
        sys.exit(1)

def interpolate_trajectories(plan, num_samples, sample_rate):
    """Interpolates keyframes to create continuous trajectories."""
    print("Interpolating trajectories from plan...")
    plan_times = [p['time'] for p in plan]

    if plan_times[0] > 0:
        plan.insert(0, plan[0].copy())
        plan[0]['time'] = 0.0
        plan_times.insert(0, 0.0)

    audio_duration = num_samples / sample_rate
    if plan_times[-1] < audio_duration:
        plan.append(plan[-1].copy())
        plan[-1]['time'] = audio_duration
        plan_times.append(audio_duration)

    sample_times = np.arange(num_samples) / sample_rate
    azimuths = np.interp(sample_times, plan_times, [p['azimuth'] for p in plan])
    elevations = np.interp(sample_times, plan_times, [p['elevation'] for p in plan])
    distances = np.interp(sample_times, plan_times, [p['distance'] for p in plan])
    reverb_mixes = np.interp(sample_times, plan_times, [p['reverb_mix'] for p in plan])

    return azimuths, elevations, distances, reverb_mixes

def apply_distance_simulation(audio_mono, distance_trajectory):
    """Applies gain based on distance trajectory."""
    print("Simulating distance with gain adjustment...")
    distance_trajectory = np.maximum(distance_trajectory, MIN_DISTANCE)
    gain_trajectory = REFERENCE_DISTANCE / distance_trajectory
    return audio_mono * gain_trajectory

def find_nearest_hrir_idx(sofa, target_azi, target_ele):
    """Finds the index of the nearest HRIR in the SOFA file."""
    source_positions = sofa.getVariableValue('SourcePosition')

    # Convert target Azimuth/Elevation to Cartesian
    target_rad_azi = np.deg2rad(target_azi)
    target_rad_ele = np.deg2rad(target_ele)
    x = np.cos(target_rad_azi) * np.cos(target_rad_ele)
    y = np.sin(target_rad_azi) * np.cos(target_rad_ele)
    z = np.sin(target_rad_ele)
    target_pos = np.array([x, y, z])

    # Convert SOFA positions (AEC) to Cartesian
    sofa_azi = source_positions[:, 0]
    sofa_ele = source_positions[:, 1]
    sofa_rad_azi = np.deg2rad(sofa_azi)
    sofa_rad_ele = np.deg2rad(sofa_ele)
    sofa_x = np.cos(sofa_rad_azi) * np.cos(sofa_rad_ele)
    sofa_y = np.sin(sofa_rad_azi) * np.cos(sofa_rad_ele)
    sofa_z = np.sin(sofa_rad_ele)
    sofa_pos_cart = np.stack([sofa_x, sofa_y, sofa_z], axis=1)

    # Find the nearest position using dot product (cosine similarity)
    distances = np.sum((sofa_pos_cart - target_pos)**2, axis=1)
    return np.argmin(distances)

def generate_dry_signal(audio_dist_adj, azi_traj, ele_traj, fs):
    """Generates the dry binaural signal using manual convolution."""
    print("Generating dry signal with manual HRTF convolution...")
    try:
        sofa = SOFAFile(HRTF_FILENAME, 'r')
        if sofa.getSamplingRate() != fs:
             print(f"Warning: HRTF sample rate ({sofa.getSamplingRate()}) differs from audio ({fs}).")
             # In a real scenario, resampling the HRIRs would be needed.
    except Exception as e:
        print(f"Error loading SOFA file '{HRTF_FILENAME}': {e}")
        print("Please ensure the HRTF file is available in the project directory.")
        sys.exit(1)

    hrir_data = sofa.getVariableValue('Data.IR')
    num_samples = len(audio_dist_adj)
    output_signal = np.zeros((num_samples, 2)) # Stereo output

    # Overlap-add processing
    step_size = BLOCK_SIZE // 2
    fade = np.hanning(BLOCK_SIZE)

    for i in range(0, num_samples, step_size):
        # Define block
        block_start = i
        block_end = min(i + BLOCK_SIZE, num_samples)
        block = np.zeros(BLOCK_SIZE)
        actual_block_size = block_end - block_start
        block[:actual_block_size] = audio_dist_adj[block_start:block_end]

        # Get angle at the center of the block
        center_idx = i + (step_size // 2)
        if center_idx >= num_samples: continue

        azi = azi_traj[center_idx]
        ele = ele_traj[center_idx]

        # Find the best HRIR for this angle
        hrir_idx = find_nearest_hrir_idx(sofa, azi, ele)
        hrir_l = hrir_data[hrir_idx, 0, :] # Left ear
        hrir_r = hrir_data[hrir_idx, 1, :] # Right ear

        # Convolve
        convolved_l = scipy.signal.fftconvolve(block, hrir_l, mode='full')
        convolved_r = scipy.signal.fftconvolve(block, hrir_r, mode='full')

        # Add to output buffer
        out_len = len(convolved_l)
        if i + out_len > num_samples:
            out_len = num_samples - i

        output_signal[i : i + out_len, 0] += convolved_l[:out_len]
        output_signal[i : i + out_len, 1] += convolved_r[:out_len]

    return output_signal


def generate_wet_signal(audio_dist_adj, fs):
    """Generates the wet reverb-only signal."""
    print("Generating wet signal with reverb...")
    board = Pedalboard([Reverb(room_size=0.5, wet_level=1.0, dry_level=0.0)])
    # Process audio and get a mono wet signal
    wet_mono = board(audio_dist_adj, sample_rate=fs)

    # The input to the board is mono, but some plugins might output stereo.
    # Let's ensure we handle both cases and return a stereo signal.
    if wet_mono.ndim == 1:
        print("Reverb output is mono, duplicating to stereo.")
        wet_signal = np.stack([wet_mono, wet_mono], axis=1)
    elif wet_mono.shape[1] == 1:
        print("Reverb output is (N, 1), duplicating to stereo.")
        wet_signal = np.concatenate([wet_mono, wet_mono], axis=1)
    else:
        wet_signal = wet_mono

    # Ensure dtype matches the rest of the pipeline
    return wet_signal.astype(np.float64)

def mix_signals_dynamically(dry_signal, wet_signal, reverb_mix_traj):
    """Mixes dry and wet signals using equal-power crossfade."""
    print("Applying dynamic Dry/Wet mixing...")
    gain_dry = np.cos(reverb_mix_traj * (np.pi / 2))
    gain_wet = np.sin(reverb_mix_traj * (np.pi / 2))

    mixed_signal = (dry_signal * gain_dry[:, np.newaxis] +
                    wet_signal * gain_wet[:, np.newaxis])
    return mixed_signal

def finalize_and_save(audio_data, fs, filename):
    """Normalizes and saves the final audio."""
    print("Finalizing audio...")
    peak_level = np.max(np.abs(audio_data))
    if peak_level > 1.0:
        print(f"Clipping detected (peak level: {peak_level:.2f}). Normalizing...")
        audio_data /= peak_level
        audio_data *= 0.99

    try:
        sf.write(filename, audio_data, fs, subtype='FLOAT')
        print(f"Successfully rendered and saved 3D binaural audio to '{filename}'")
    except Exception as e:
        print(f"Error writing output WAV file: {e}")
        sys.exit(1)

def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <path_to_input_audio> <path_to_plan_json>")
        sys.exit(1)

    audio_filepath = sys.argv[1]
    plan_filepath = sys.argv[2]

    print("--- Phase 2: Dynamic Audio Rendering ---")

    audio_mono, fs = load_audio(audio_filepath)
    plan = load_plan(plan_filepath)
    num_samples = len(audio_mono)
    azi, ele, dist, reverb_mix = interpolate_trajectories(plan, num_samples, fs)
    audio_dist_adj = apply_distance_simulation(audio_mono, dist)

    # Generate Dry signal (HRTF)
    dry_signal = generate_dry_signal(audio_dist_adj, azi, ele, fs)

    # Generate Wet signal (Reverb)
    wet_signal = generate_wet_signal(audio_dist_adj, fs)

    # Dynamic mixing
    # Ensure reverb_mix trajectory has the same length as the signals
    if len(reverb_mix) != len(dry_signal):
        reverb_mix = np.interp(np.arange(len(dry_signal)),
                               np.linspace(0, 1, len(reverb_mix)),
                               reverb_mix)

    final_audio = mix_signals_dynamically(dry_signal, wet_signal, reverb_mix)

    finalize_and_save(final_audio, fs, OUTPUT_FILENAME)

    print("--- Phase 2 Complete ---")

if __name__ == "__main__":
    main()
