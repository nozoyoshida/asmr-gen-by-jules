# AI-Driven 3D Binaural ASMR Audio Generation System

This project is a system that automatically generates immersive 3D binaural ASMR audio files (WAV) from a monaural voice input and a timestamped script.

The core of this system is its ability to dynamically control the sound source's position, distance, and spatial reverberation based on an AI's (Google Gemini) understanding of the script's context.

## Features

- **AI-Powered Spatial Direction**: Gemini API analyzes the script to create a natural and immersive spatial audio plan.
- **Dynamic Audio Rendering**: Utilizes Head-Related Transfer Functions (HRTF), distance simulation, and reverberation effects that change over time based on the plan.
- **High-Quality Audio**: All internal processing is done at 44.1kHz, and the output is a high-quality WAV file.

## System Architecture

The system consists of two independent phases (scripts):

1.  **`generate_plan.py`**: Analyzes the script using the Gemini API and generates a spatial direction plan (JSON).
2.  **`render_audio.py`**: Renders the 3D binaural audio based on the JSON plan and the input audio file.

## Requirements

The required Python libraries are listed in `requirements.txt`.

- `google-generativeai`
- `pedalboard`
- `numpy`
- `scipy`
- `soundfile`
- `python-dotenv`
- `pysofaconventions`

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up your API key:**
    - Rename the `.env.example` file to `.env`.
    - Open the `.env` file and replace `"YOUR_API_KEY"` with your actual Google Gemini API key.
    ```
    GEMINI_API_KEY="xxxxxxxxxxxxxxxxxxxxxxx"
    ```

4.  **Download the HRTF data:**
    This project requires a Head-Related Transfer Function (HRTF) dataset in the SOFA format. We will use a standard dataset from the ARI (Acoustics Research Institute) database.
    Run the following command in your terminal to download the file and name it `hrtf.sofa`:
    ```bash
    wget "https://projects.ari.oeaw.ac.at/research/experimental_audiology/hrtf/database/ItE/SOFA/NH2/hrtf_M_hrtf%20B.sofa" -O hrtf.sofa
    ```
    If the link is broken, please search for a standard SOFA HRTF file and place it in the root of the project directory as `hrtf.sofa`.

## How to Run

You will need a monaural audio file (e.g., `input.wav`) and a timestamped script file (e.g., `script.txt`). A sample script is provided as `sample_script.txt`.

### Step 1: Generate the Spatial Direction Plan

Run `generate_plan.py` with the path to your script file. This requires your Gemini API key to be set.

```bash
python generate_plan.py sample_script.txt
```

This will generate a `panning_plan.json` file in the project root.

### Step 2: Render the 3D Binaural Audio

Run `render_audio.py` with the paths to your input audio file and the generated plan file.

```bash
# Make sure you have an input.wav file
python render_audio.py input.wav panning_plan.json
```

This will generate the final `output.wav` file, which is your 3D binaural audio.
