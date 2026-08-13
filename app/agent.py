# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback


MODEL = "gemini-3.6-flash"
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-54645ed9a07f"
GCS_BUCKET_NAME = "smart-pantry-assets-qwiklabs-gcp-03-54645ed9a07f"
AGENT_ENGINE_RESOURCE_NAME = "projects/135622055779/locations/us-east1/reasoningEngines/4121585307416002560"
COLLECTION_NAME = "pantry_inventory"




async def generate_memories_callback(callback_context: CallbackContext):
    """Sends session events to Memory Bank for extraction after each turn."""
    await callback_context.add_session_to_memory()
    return None


def _get_firestore_client() -> firestore.Client:
    """Creates a Firestore client targeting the hardcoded project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)



def query_pantry_inventory(status_filter: str = "available") -> str:
    """Queries and reads pantry items from the Firestore collection 'pantry_inventory'.

    Args:
        status_filter: Filter by item status ('available', 'expended', or 'all'). Default is 'available'.

    Returns:
        Formatted text summary of pantry items stored in Firestore.
    """
    db = _get_firestore_client()
    col_ref = db.collection(COLLECTION_NAME)

    if status_filter.lower() != "all":
        docs = col_ref.where(filter=firestore.FieldFilter("status", "==", status_filter.lower())).stream()
    else:
        docs = col_ref.stream()


    items = []
    for doc in docs:
        data = doc.to_dict()
        data["doc_id"] = doc.id
        items.append(data)

    if not items:
        return f"No items found in Firestore collection '{COLLECTION_NAME}' with status='{status_filter}'."

    summary_lines = [f"Found {len(items)} item(s) in Firestore '{COLLECTION_NAME}':"]
    for item in items:
        summary_lines.append(
            f"- [{item.get('doc_id')}] {item.get('item_name')} ({item.get('quantity')}) | "
            f"Category: {item.get('category')} | Expires: {item.get('expiration_date')} | "
            f"Status: {item.get('status')}"
        )
    return "\n".join(summary_lines)


def add_or_update_pantry_item_firestore(
    item_id: str,
    item_name: str,
    category: str,
    quantity: str,
    expiration_date: str = "",
    notes: str = "",
) -> str:
    """Writes or updates a pantry item document in the Firestore collection 'pantry_inventory'.

    Args:
        item_id: Unique identifier for the item (e.g. 'chicken_breast', 'baby_spinach').
        item_name: Display name of the ingredient (e.g. 'Chicken Breast').
        category: Item category (e.g. 'Meat & Seafood', 'Produce', 'Dairy', 'Pantry').
        quantity: Quantity string (e.g. '2 lbs', '1 bag').
        expiration_date: Expiration date string in YYYY-MM-DD format (optional).
        notes: Additional notes or source info (optional).

    Returns:
        Confirmation message detailing the updated document in Firestore.
    """
    db = _get_firestore_client()
    clean_id = item_id.strip().lower().replace(" ", "_")
    doc_ref = db.collection(COLLECTION_NAME).document(clean_id)

    doc_data = {
        "item_name": item_name,
        "category": category,
        "quantity": quantity,
        "expiration_date": expiration_date,
        "status": "available",
        "notes": notes,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    doc_ref.set(doc_data, merge=True)
    return (
        f"SUCCESS: Saved item '{item_name}' (ID: {doc_ref.id}) into Firestore collection '{COLLECTION_NAME}' "
        f"with quantity '{quantity}'."
    )


def expend_pantry_item_firestore(item_id: str, recipe_cooked: str = "") -> str:
    """Updates a pantry item document status to 'expended' in the Firestore collection 'pantry_inventory'.

    Args:
        item_id: Unique identifier key of the pantry item document (e.g. 'chicken_breast').
        recipe_cooked: Name of the recipe prepared (optional).

    Returns:
        Confirmation message showing status update in Firestore.
    """
    db = _get_firestore_client()
    clean_id = item_id.strip().lower().replace(" ", "_")
    doc_ref = db.collection(COLLECTION_NAME).document(clean_id)
    doc = doc_ref.get()

    if not doc.exists:
        return f"ERROR: Item ID '{clean_id}' not found in Firestore collection '{COLLECTION_NAME}'."

    doc_ref.update({
        "status": "expended",
        "expended_in_recipe": recipe_cooked,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    return (
        f"SUCCESS: Marked item ID '{clean_id}' as 'expended' in Firestore "
        f"(recipe cooked: '{recipe_cooked}')."
    )


def record_allergies(allergies: list[str]) -> str:
    """Records and updates the user's food allergies, sensitivities, and dietary restrictions.

    Args:
        allergies: List of food allergies, sensitivities, or dietary restrictions (e.g. ['peanuts', 'shellfish', 'dairy-free']).

    Returns:
        Confirmation message detailing recorded allergies.
    """
    formatted = ", ".join(allergies)
    return (
        f"SUCCESS: Recorded user allergy profile: [{formatted}]. "
        "These restrictions are saved to long-term memory and will be strictly enforced across all recipe suggestions."
    )


def add_pantry_items_from_receipt_or_photo(
    items: list[str], source_description: str = "receipt/photo"
) -> str:
    """Catalogs ingredients identified from uploaded grocery receipt photos or pantry/fridge images into active inventory.

    Args:
        items: List of ingredient items identified from the receipt or photo (e.g. ['chicken breast', 'spinach', 'heavy cream', 'olive oil']).
        source_description: Brief description of the source (e.g. 'Whole Foods receipt', 'refrigerator top shelf').

    Returns:
        Confirmation message listing newly cataloged items.
    """
    formatted_items = ", ".join(items)
    return (
        f"SUCCESS: Added {len(items)} items from {source_description} to pantry inventory: [{formatted_items}]. "
        "Inventory is saved to memory for meal planning."
    )


def expend_pantry_items(items: list[str], recipe_cooked: str) -> str:
    """Deducts and records ingredients used/expended when cooking a specific recipe.

    Args:
        items: List of ingredients used/expended (e.g. ['spinach', 'heavy cream']).
        recipe_cooked: Name of the recipe prepared (e.g. 'Creamy Spinach Pasta').

    Returns:
        Confirmation message showing expended items and updated pantry state.
    """
    formatted_items = ", ".join(items)
    return (
        f"SUCCESS: Expended ingredients [{formatted_items}] for recipe '{recipe_cooked}'. "
        "Active pantry inventory has been updated in memory."
    )


def generate_grocery_shopping_list(required_ingredients: list[str]) -> str:
    """Compares required recipe ingredients against available items in the Firestore collection 'pantry_inventory' and generates a shopping list for missing items.

    Args:
        required_ingredients: List of ingredients needed for a planned recipe or meal plan (e.g. ['chicken breast', 'heavy cream', 'tomatoes', 'basil']).

    Returns:
        Formatted summary listing available items found in pantry and missing items needed on the shopping list.
    """
    db = _get_firestore_client()
    docs = db.collection(COLLECTION_NAME).where(filter=firestore.FieldFilter("status", "==", "available")).stream()

    pantry_item_names = set()
    for doc in docs:
        data = doc.to_dict()
        if name := data.get("item_name"):
            pantry_item_names.add(name.lower().strip())

    missing_items = []
    available_in_pantry = []

    for req in required_ingredients:
        clean_req = req.lower().strip()
        if any(pantry_name in clean_req or clean_req in pantry_name for pantry_name in pantry_item_names):
            available_in_pantry.append(req)
        else:
            missing_items.append(req)

    result_lines = ["🛒 Grocery Shopping List Analysis:"]
    if available_in_pantry:
        result_lines.append(f"✅ Available in Pantry ({len(available_in_pantry)}): " + ", ".join(available_in_pantry))
    if missing_items:
        result_lines.append(f"🛒 Need to Buy / Missing ({len(missing_items)}): " + ", ".join(missing_items))
    else:
        result_lines.append("🎉 You have all required ingredients in your pantry!")

    return "\n".join(result_lines)


RAG_CORPUS_NAME = "projects/135622055779/locations/us-central1/ragCorpora/9114766676309573632"


def consult_historic_cookbook(query: str) -> str:
    """Searches the 1814 Domestic Cookery historic cookbook corpus and returns matching recipes, techniques, and culinary advice.

    Args:
        query: Recipe, ingredient preparation, or cooking technique to look up in the 1814 historic cookbook (e.g. 'roast fowl', 'preserving butter', 'stewing beef').

    Returns:
        Matched historic recipes and passages extracted from the 1814 cookbook.
    """
    import vertexai
    from vertexai.preview import rag

    try:
        vertexai.init(project=FIRESTORE_PROJECT_ID, location="us-central1")
        resp = rag.retrieval_query(
            text=query,
            rag_resources=[rag.RagResource(rag_corpus=RAG_CORPUS_NAME)],
            rag_retrieval_config=rag.RagRetrievalConfig(top_k=4),
        )
        contexts = getattr(resp.contexts, "contexts", [])
        passages = [c.text.strip() for c in contexts if getattr(c, "text", "").strip()]
        return "\n\n---\n\n".join(passages) or "No relevant historic cookbook passages found."
    except Exception as e:
        return f"Historic cookbook retrieval failed: {e}"


def generate_recipe_dish_image(
    dish_name: str,
    description: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates a photograph of a proposed dish or recipe using gemini-3.1-flash-lite-image in the global region, saves it to Playground Artifacts, uploads it to public Cloud Storage, and returns its public URL.

    Args:
        dish_name: Name of the dish or recipe (e.g. 'Garlic Butter Roasted Chicken').
        description: Additional visual description or styling details (optional).

    Returns:
        Public GCS HTTPS URL of the generated image.
    """
    prompt = f"A mouth-watering, professional studio food photograph of {dish_name}. {description}".strip()

    # 1. Generate image using gemini-3.1-flash-lite-image in global region
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
    )

    part = response.candidates[0].content.parts[0]
    image_bytes = part.inline_data.data

    clean_name = dish_name.lower().strip().replace(" ", "_").replace("/", "_")
    timestamp = int(datetime.datetime.now().timestamp())
    filename = f"{clean_name}_{timestamp}.jpg"

    # 2. Save artifact with tool_context.save_artifact if provided
    if tool_context is not None:
        try:
            artifact_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            tool_context.save_artifact(filename=filename, artifact=artifact_part)
        except Exception as e:
            print(f"Note on saving artifact in tool_context: {e}")

    # 3. Upload image bytes directly to public Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(f"dishes/{filename}")
    blob.upload_from_string(image_bytes, content_type="image/jpeg")

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/dishes/{filename}"
    return f"SUCCESS: Generated dish image for '{dish_name}'. Public image URL: {public_url}"


def generate_recipe_dish_video(
    dish_name: str,
    description: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates a short video preview for a dish, recipe, or pantry item using gemini-omni-flash-preview.

    Args:
        dish_name: Name of the dish or recipe (e.g. 'Garlic Butter Roasted Chicken').
        description: Additional visual description or cooking technique details (optional).

    Returns:
        Public GCS HTTPS URL of the generated video.
    """
    prompt = f"A short, high quality, appetizing 5-second video preview showing {dish_name}. {description}".strip()

    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
    interaction = client.interactions.create(
        model="gemini-omni-flash-preview",
        input=prompt,
    )

    video_bytes = None
    if getattr(interaction, "output_video", None) and getattr(interaction.output_video, "data", None):
        video_bytes = interaction.output_video.data
    elif getattr(interaction, "outputs", None):
        for out in interaction.outputs:
            d = getattr(out, "data", None) if not isinstance(out, dict) else out.get("data")
            if d:
                video_bytes = d
                break

    if not video_bytes:
        return f"ERROR: No video bytes generated for '{dish_name}'."

    clean_name = dish_name.lower().strip().replace(" ", "_").replace("/", "_")
    timestamp = int(datetime.datetime.now().timestamp())
    filename = f"{clean_name}_{timestamp}.mp4"

    # 1. Save artifact with tool_context.save_artifact if provided
    if tool_context is not None:
        try:
            artifact_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
            tool_context.save_artifact(filename=filename, artifact=artifact_part)
        except Exception as e:
            print(f"Note on saving artifact in tool_context: {e}")

    # 2. Upload video bytes directly to public Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(f"videos/{filename}")
    blob.upload_from_string(video_bytes, content_type="video/mp4")

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/videos/{filename}"
    return f"SUCCESS: Generated dish video for '{dish_name}'. Public video URL: {public_url}"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
)


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="Smart Pantry & Recipe Concierge, a stateful culinary AI assistant backed by Firestore database and a grounded 1814 Historic Cookbook RAG Corpus.",
    workflow_description=(
        "Your core responsibilities:\n"
        "1. **Allergies & Dietary Restrictions**: Always record and enforce user food allergies, sensitivities, and dietary preferences across conversations using `record_allergies`. Never suggest recipes containing identified allergens.\n"
        "2. **Pantry Cataloging & Firestore**: When users upload receipt photos, fridge images, or list groceries, extract all ingredients and call `add_or_update_pantry_item_firestore` (and `add_pantry_items_from_receipt_or_photo`) to save them into the Firestore collection 'pantry_inventory'.\n"
        "3. **Inventory Querying**: Use `query_pantry_inventory` to read available items from Firestore when planning meals or checking stock.\n"
        "4. **Dish Image Generation**: Call `generate_recipe_dish_image` to generate a mouth-watering photograph of proposed dishes or recipes, save it as an artifact, and return its public URL.\n"
        "5. **Dish Video Generation**: Call `generate_recipe_dish_video` to generate a short video preview of proposed dishes or recipes using gemini-omni-flash-preview, save it as an artifact, and return its public URL.\n"
        "6. **Historic Cookbook Knowledge**: Call `consult_historic_cookbook` to retrieve authentic recipes, preservation techniques, and domestic economy principles from the 1814 Domestic Cookery corpus.\n"
        "7. **Shopping List Generation**: Use `generate_grocery_shopping_list` to compare required recipe ingredients against Firestore pantry stock and generate missing item shopping lists.\n"
        "8. **Ingredient Deduction**: When the user cooks a recipe, call `expend_pantry_item_firestore` to mark ingredients as expended in Firestore.\n"
        "9. **Meal Planning & A2UI UI**: Suggest recipes that maximize available pantry items while strictly avoiding user allergens. Return structured A2UI cards/UI when appropriate."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        query_pantry_inventory,
        generate_recipe_dish_image,
        generate_recipe_dish_video,
        consult_historic_cookbook,
        generate_grocery_shopping_list,
        add_or_update_pantry_item_firestore,
        expend_pantry_item_firestore,
        record_allergies,
        add_pantry_items_from_receipt_or_photo,
        expend_pantry_items,
        get_weather,
        get_current_time,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)






app = App(
    root_agent=root_agent,
    name="app",
)


