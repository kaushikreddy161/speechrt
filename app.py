import os
from flask import Flask, request, jsonify
import azure.cognitiveservices.speech as speechsdk
import threading
import queue
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)

# Enable CORS for the frontend origin and allow GET, POST, and OPTIONS methods
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# Azure credentials
speech_key = os.environ.get('AZURE_SPEECH_KEY','d7f1bae7919b41479575a01b73316bb6')
service_region = os.environ.get('AZURE_SPEECH_REGION','australiaeast')
endpoint = os.environ.get('AZURE_SPEECH_ENDPOINT','https://australiaeast.api.cognitive.microsoft.com/')

translation_history = []
current_partial_text = ""
is_recording = False
result_queue = queue.Queue()

@app.route('/')
def welcome():
    return jsonify({
        "message": "Welcome to the Real-Time Speech Translator API!",
        "version": "1.0",
        "instructions": "To use this API, make POST requests to start and stop recording, and GET requests to retrieve translations. Ensure you have the necessary permissions and API key to access these endpoints."
    })

@app.route('/api/start_recording', methods=['POST'])
def start_recording():
    global is_recording
    if not is_recording:
        is_recording = True
        source_lang = request.json['source_lang']
        target_lang = request.json['target_lang']
        threading.Thread(target=start_translation, args=(source_lang, target_lang)).start()
        return jsonify({"status": "started"})
    return jsonify({"status": "already_recording"})

@app.route('/api/stop_recording', methods=['POST'])
def stop_recording():
    global is_recording, current_recognizer
    is_recording = False
    if current_recognizer:
        current_recognizer.stop_continuous_recognition()
    return jsonify({"status": "stopped"})

@app.route('/api/get_translation')
def get_translation():
    try:
        result = result_queue.get_nowait()
        translation_history.append(result)
        current_partial_text = ""
    except queue.Empty:
        result = None
    
    return jsonify({
        "history": translation_history,
        "partial": current_partial_text
    })

@app.route('/api/clear_history', methods=['POST'])
def clear_history():
    global translation_history, current_partial_text
    translation_history = []
    current_partial_text = ""
    return jsonify({"status": "cleared"})

@app.route('/api/languages')
def get_languages():
    return jsonify({
        "target_languages": sorted(target_languages.keys()),
        "speech_recognition_languages": sorted(speech_recognition_languages.keys())
    })

def start_translation(source_lang, target_lang):
    global current_partial_text, is_recording, current_recognizer

    try:
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        translation_config = speechsdk.translation.SpeechTranslationConfig(
            subscription=speech_key,
            region=service_region
        )
        translation_config.speech_recognition_language = speech_recognition_languages[source_lang]
        translation_config.add_target_language(target_languages[target_lang])

        current_recognizer = speechsdk.translation.TranslationRecognizer(
            translation_config=translation_config,
            audio_config=audio_config
        )

        def handle_result(event):
            global current_partial_text
            if event.result.reason == speechsdk.ResultReason.TranslatedSpeech:
                translations = event.result.translations
                translated_text = translations.get(target_languages[target_lang], "Translation not available")
                if translated_text.strip():
                    result_queue.put(translated_text)

        def handle_intermediate_result(event):
            global current_partial_text
            if event.result.reason == speechsdk.ResultReason.TranslatingSpeech:
                translations = event.result.translations
                translated_text = translations.get(target_languages[target_lang], "")
                if translated_text.strip():
                    current_partial_text = translated_text

        current_recognizer.recognized.connect(handle_result)
        current_recognizer.recognizing.connect(handle_intermediate_result)
        current_recognizer.start_continuous_recognition()

        while is_recording:
            pass

        current_recognizer.stop_continuous_recognition()
        
    except Exception as e:
        print(f"Error in translation: {str(e)}")
        is_recording = False


# Uncomment if running locally
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
