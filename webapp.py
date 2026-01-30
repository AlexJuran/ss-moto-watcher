from __future__ import annotations

from flask import Flask, render_template, request

from SSka import find_matches  # импортируем твою функцию


app = Flask(__name__)


@app.get("/")
def index():
    # Параметры из URL (чтобы можно было менять прямо в адресной строке)
    limit = int(request.args.get("limit", 35))
    max_price = int(request.args.get("max_price", 6000))
    cc_min = int(request.args.get("cc_min", 350))
    cc_max = int(request.args.get("cc_max", 750))

    brands_raw = request.args.get("brands", "Kawasaki,Honda,BMW,Suzuki,Yamaha,Triumph")
    models_raw = request.args.get("models", "dr,drz,xr,klr,klx,dl650,vstrom,freewind,transalp")

    brands = [b.strip() for b in brands_raw.split(",") if b.strip()]
    models = [m.strip() for m in models_raw.split(",") if m.strip()]

    items = find_matches(
        limit=limit,
        max_price=max_price,
        cc_min=cc_min,
        cc_max=cc_max,
        brands=brands,
        query_models=models,
        debug_seen=False,
        delay_seconds=0.0,
    )

    return render_template(
        "index.html",
        items=items,
        limit=limit,
        max_price=max_price,
        cc_min=cc_min,
        cc_max=cc_max,
        brands_raw=brands_raw,
        models_raw=models_raw,
    )


if __name__ == "__main__":
    app.run(debug=True)
