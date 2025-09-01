import os
import sys
import json
import google.generativeai as genai
from dotenv import load_dotenv

# --- Constants ---
OUTPUT_FILENAME = "panning_plan.json"
MODEL_NAME = "gemini-1.5-flash" # Using a fast and capable model

# --- JSON Schema for Validation ---
PLAN_JSON_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "time": {"type": "number"},
            "azimuth": {"type": "number"},
            "elevation": {"type": "number"},
            "distance": {"type": "number"},
            "reverb_mix": {"type": "number", "minimum": 0.0, "maximum": 1.0}
        },
        "required": ["time", "azimuth", "elevation", "distance", "reverb_mix"]
    }
}


def load_api_key():
    """Load Gemini API key from .env file."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found. Please create a .env file and add your API key.")
        sys.exit(1)
    return api_key


def read_script_file(filepath):
    """Read the content of the script file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Script file not found at '{filepath}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading script file: {e}")
        sys.exit(1)


def get_system_prompt():
    """Returns the system prompt for the Gemini API call."""
    return """
You are a professional ASMR sound director.
Your task is to analyze the provided timestamped script and create a sound direction plan in JSON format to provide the listener with the best immersive experience.
You must strictly adhere to the following rules.

1.  **Role**: Your job is to design how the voice sounds over time, including where it comes from, how close it is, and how the space reverberates.
2.  **Output Format**: Your response must be exclusively in the specified JSON format. Do not include any other text, explanations, or markdown formatting.
3.  **Direction Hints**:
    *   **Whispers**: For whispers, set `distance` to be very close (e.g., 0.2 to 0.3 meters) and reduce `reverb_mix` to almost 0.
    *   **Movement**: If the script indicates movement like "from right to left," smoothly vary the `azimuth`.
    *   **Emotion**: Adjust `distance` and `reverb_mix` to match emotional highs and lows or moments of silence.
    *   **Naturalness**: Plan for smooth transitions between keyframes. Avoid abrupt changes in parameters.
    *   **Start and End**: It's good practice to start and end the story at a neutral position (e.g., `azimuth=0`, `distance=1.0`).

**JSON Schema to follow:**
```json
[
    {
        "time": float,       // Keyframe time in seconds.
        "azimuth": float,    // Horizontal angle in degrees. Front=0, Right=90, Left=-90.
        "elevation": float,  // Vertical angle in degrees. Horizontal=0, Up=90, Down=-90.
        "distance": float,   // Distance in meters. e.g., ear-side=0.2, standard=1.0.
        "reverb_mix": float  // Dry/Wet mix for reverb (0.0 to 1.0).
    }
]
```
"""


def validate_plan(plan_data):
    """
    Validates the generated plan against the schema.
    A simple implementation for now. A more robust validation could use jsonschema library.
    """
    if not isinstance(plan_data, list):
        print("Validation Error: The root of the JSON must be a list.")
        return False

    for item in plan_data:
        if not isinstance(item, dict):
            print(f"Validation Error: Item is not an object: {item}")
            return False

        required_keys = PLAN_JSON_SCHEMA["items"]["required"]
        for key in required_keys:
            if key not in item:
                print(f"Validation Error: Missing key '{key}' in item: {item}")
                return False

        for key, value in item.items():
            prop_type = PLAN_JSON_SCHEMA["items"]["properties"][key]["type"]
            if prop_type == "number" and not isinstance(value, (int, float)):
                 print(f"Validation Error: Key '{key}' must be a number, but got {type(value)} in item: {item}")
                 return False

    return True


def generate_plan(api_key, script_content):
    """
    Generates the spatial direction plan using the Gemini API.
    """
    print("Connecting to Gemini API to generate the spatial plan...")
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        MODEL_NAME,
        system_instruction=get_system_prompt(),
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json"
        )
    )

    user_prompt = f"Please create a sound direction plan for the following script:\n\n```\n{script_content}\n```"

    try:
        response = model.generate_content(user_prompt)
        # The response text should be a valid JSON string.
        plan_data = json.loads(response.text)

        print("Successfully received plan from API. Validating...")
        if not validate_plan(plan_data):
            print("Error: The generated JSON plan is invalid.")
            sys.exit(1)

        return plan_data

    except json.JSONDecodeError:
        print("Error: Failed to decode JSON from Gemini API response.")
        print("--- API Response Text ---")
        print(response.text)
        print("-------------------------")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred while communicating with the Gemini API: {e}")
        sys.exit(1)


def save_plan(plan_data, filename):
    """Saves the plan data to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, indent=4)
        print(f"Successfully saved spatial plan to '{filename}'")
    except Exception as e:
        print(f"Error saving plan to file: {e}")
        sys.exit(1)


def main():
    """Main function to run the script."""
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_script_file>")
        sys.exit(1)

    script_filepath = sys.argv[1]

    print("--- Phase 1: Generating Spatial Direction Plan ---")

    # 1. Load API Key
    api_key = load_api_key()

    # 2. Read script file
    script_content = read_script_file(script_filepath)

    # 3. Generate plan via API
    plan = generate_plan(api_key, script_content)

    # 4. Save the plan
    save_plan(plan, OUTPUT_FILENAME)

    print("--- Phase 1 Complete ---")


if __name__ == "__main__":
    main()
