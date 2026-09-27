import os
from flask import Flask, render_template, jsonify, request
from src.m4_integration.metrics import GLOBAL_METRICS
from src.m4_integration.facade import GLOBAL_FACADE
from src.m1_storage.defrag import defragment
from src.m4_integration.benchmark import run_benchmark

app = Flask(__name__, template_folder="templates")

# Initialize storage and boot sequence when dashboard app starts
try:
    if os.path.exists("disk.img"):
        GLOBAL_FACADE.storage.mount_disk("disk.img")
    else:
        GLOBAL_FACADE.storage.format_disk("disk.img", size_bytes=67108864, mode="FAT")
except Exception:
    pass

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/metrics", methods=["GET"])
def get_metrics():
    data = GLOBAL_METRICS.get_dashboard_data()
    return jsonify(data)

@app.route("/api/defrag", methods=["POST"])
def trigger_defrag():
    req = request.get_json(silent=True) or {}
    path = req.get("path")
    try:
        if path:
            defragment(path, GLOBAL_FACADE.storage)
        else:
            # Defragment all files
            files = [p for p, e in GLOBAL_FACADE.storage.directories.items() if e.entry_type == "file"]
            for f in files:
                defragment(f, GLOBAL_FACADE.storage)
        return jsonify({"status": "success", "message": "Defragmentation completed"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/benchmark", methods=["POST"])
def trigger_benchmark():
    try:
        res = run_benchmark("mixed", num_ops=15)
        return jsonify(res)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
