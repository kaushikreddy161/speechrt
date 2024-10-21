import os
from flask import Flask, request, jsonify
import azure.cognitiveservices.speech as speechsdk
import threading
import queue
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://127.0.0.1:5500"}})

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
        "endpoints": {
            "start_recording": "/api/start_recording",
            "stop_recording": "/api/stop_recording",
            "get_translation": "/api/get_translation",
            "clear_history": "/api/clear_history"
        },
        "instructions": "To use this API, make POST requests to start and stop recording, and GET requests to retrieve translations. Ensure you have the necessary permissions and API key to access these endpoints."
    })

@app.route('/api/start_recording', methods=['POST'])
def start_recording():
    global is_recording
    if not is_recording:
        is_recording = True
        data = request.json
        source_lang = data['source_lang']
        target_lang = data['target_lang']
        threading.Thread(target=start_translation, args=(source_lang, target_lang)).start()
        return jsonify({"status": "started"})
    return jsonify({"status": "already_recording"})

@app.route('/api/stop_recording', methods=['POST'])
def stop_recording():
    global is_recording
    is_recording = False
    return jsonify({"status": "stopped"})

@app.route('/api/get_translation', methods=['GET'])
def get_translation():
    global current_partial_text
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

def start_translation(source_lang, target_lang):
    global current_partial_text, is_recording

    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    translation_config = speechsdk.translation.SpeechTranslationConfig(
        subscription=speech_key,
        region=service_region
    )
    translation_config.speech_recognition_language = source_lang
    translation_config.add_target_language(target_lang)

    translator = speechsdk.translation.TranslationRecognizer(
        translation_config=translation_config,
        audio_config=audio_config
    )

    def handle_result(event):
        global current_partial_text
        if event.result.reason == speechsdk.ResultReason.TranslatedSpeech:
            translations = event.result.translations
            translated_text = translations.get(target_lang, "Translation not available")
            if translated_text.strip():
                result_queue.put(translated_text)

    def handle_intermediate_result(event):
        global current_partial_text
        if event.result.reason == speechsdk.ResultReason.TranslatingSpeech:
            translations = event.result.translations
            translated_text = translations.get(target_lang, "")
            if translated_text.strip():
                current_partial_text = translated_text

    translator.recognized.connect(handle_result)
    translator.recognizing.connect(handle_intermediate_result)

    translator.start_continuous_recognition()

    while is_recording:
        pass

    translator.stop_continuous_recognition()

#if __name__ == '__main__':
#    app.run(host='0.0.0.0', port=8000, debug=True)
