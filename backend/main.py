from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from contextlib import asynccontextmanager
import uvicorn, os, asyncio, time, uuid, json, re
from pathlib import Path
import aiofiles

from generator import UICodeGenerator, build_prompt, SYSTEM_PROMPT, GROQ_MODEL, GROQ_MODEL_FAST, MODEL_BACKEND

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
TTL_SECONDS = 3600
generator   = UICodeGenerator()

async def cleanup_uploads():
    while True:
        await asyncio.sleep(300)
        now = time.time()
        for f in UPLOAD_DIR.iterdir():
            try:
                if f.is_file() and (now - f.stat().st_mtime) > TTL_SECONDS:
                    f.unlink()
            except Exception:
                pass

@asynccontextmanager
async def lifespan(_):
    asyncio.create_task(cleanup_uploads())
    yield

app = FastAPI(title="Ink2Interface API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def save_images(images):
    paths = []
    for img in images:
        if img.filename:
            fpath = UPLOAD_DIR / f"{uuid.uuid4()}{Path(img.filename).suffix}"
            async with aiofiles.open(fpath, "wb") as f:
                await f.write(await img.read())
            paths.append(str(fpath))
    return paths


# ── Streaming endpoint ────────────────────────────────────────────────────────
@app.post("/generate/stream")
async def generate_stream(
    prompt:      str = Form(default=""),
    tech_stack:  str = Form(default="html-tailwind"),
    model_tier:  str = Form(default="ink2interface-balanced"),
    source_url:  str = Form(default=""),
    source_html: str = Form(default=""),
    images: list[UploadFile] = File(default=[]),
):
    if not images and not prompt and not source_url and not source_html:
        raise HTTPException(400, "Provide at least one input.")

    image_paths = await save_images(images)

    async def event_stream():
        try:
            parts = await build_prompt(image_paths, prompt, source_url, source_html, tech_stack)
            has_images = any(p.get("type") == "image_url" for p in parts)
            model = GROQ_MODEL if has_images else GROQ_MODEL_FAST

            # Access the underlying Groq client (only available in groq backend mode)
            if MODEL_BACKEND != "groq":
                # Fall back to non-streaming for local models
                result = await generator.generate(
                    image_paths=image_paths, prompt=prompt,
                    source_url=source_url, source_html=source_html,
                    tech_stack=tech_stack, model_tier=model_tier,
                )
                yield f"data: {json.dumps({'token': result['code']})}\n\n"
                yield f"data: {json.dumps({'done': True, 'tech_stack': tech_stack, 'model': result['model']})}\n\n"
                return

            groq_client = generator._backend.client
            stream = await groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": parts},
                ],
                max_tokens=8192,
                temperature=0.1,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    # SSE format
                    yield f"data: {json.dumps({'token': delta})}\n\n"

            yield f"data: {json.dumps({'done': True, 'tech_stack': tech_stack, 'model': model})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            for p in image_paths:
                try: os.remove(p)
                except Exception: pass

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Non-streaming fallback ────────────────────────────────────────────────────
@app.post("/generate")
async def generate_code(
    prompt:      str = Form(default=""),
    tech_stack:  str = Form(default="html-tailwind"),
    model_tier:  str = Form(default="ink2interface-balanced"),
    source_url:  str = Form(default=""),
    source_html: str = Form(default=""),
    images: list[UploadFile] = File(default=[]),
):
    image_paths = await save_images(images)
    if not image_paths and not prompt and not source_url and not source_html:
        raise HTTPException(400, "Provide at least one input.")
    try:
        result = await generator.generate(
            image_paths=image_paths, prompt=prompt,
            source_url=source_url, source_html=source_html,
            tech_stack=tech_stack, model_tier=model_tier,
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        for p in image_paths:
            try: os.remove(p)
            except Exception: pass


@app.get("/health")
def health():
    return {"status": "ok", "model": generator.model_name}

@app.get("/stacks")
def stacks():
    return {"stacks": [
        {"id": "html-tailwind",  "label": "HTML + Tailwind CSS"},
        {"id": "react-tailwind", "label": "React + Tailwind CSS"},
        {"id": "vue",            "label": "Vue 3 + Tailwind CSS"},
        {"id": "svelte",         "label": "Svelte + Tailwind CSS"},
        {"id": "nextjs",         "label": "Next.js + Tailwind CSS"},
    ]}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
