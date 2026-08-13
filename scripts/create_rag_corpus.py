# Copyright 2026 Google LLC
#
# Script to create a serverless Vertex AI RAG Engine corpus
# and import/index the 1814 Domestic Cookery PDF from GCS.

import vertexai
from vertexai.preview import rag
from vertexai.preview.rag.utils import resources as rr

PROJECT_ID = "qwiklabs-gcp-03-54645ed9a07f"
LOCATION = "us-central1"  # Serverless RAG Engine is us-central1
GCS_PATH = "gs://smart-pantry-assets-qwiklabs-gcp-03-54645ed9a07f/cookbooks/a_new_system_of_domestic_cookery-formed_upon_principles_of_economy_1814.pdf"

PARSING_PROMPT = (
    "Extract individual culinary recipes, ingredient preparations, cooking techniques, "
    "and domestic food economy principles described in this historic cookbook text. "
    "Ignore boilerplate, publication details, and page numbers. Output clean, self-contained prose."
)


def create_and_index_rag_corpus():
    print(f"Initializing Vertex AI in project '{PROJECT_ID}', location '{LOCATION}'...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    print("1. Updating RAG Engine config to serverless mode...")
    cfg = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragEngineConfig"
    try:
        rag.update_rag_engine_config(
            rag_engine_config=rag.RagEngineConfig(
                name=cfg,
                rag_managed_db_config=rag.RagManagedDbConfig(mode=rr.Serverless()),
            )
        )
        print("   ✓ Serverless mode enabled.")
    except Exception as e:
        print(f"   Note on serverless config update: {e}")

    print("2. Creating RAG corpus 'domestic-cookery-1814'...")
    corpus = rag.create_corpus(
        display_name="domestic-cookery-1814",
        embedding_model_config=rag.EmbeddingModelConfig(
            publisher_model="publishers/google/models/text-embedding-005"
        ),
    )
    print(f"   ✓ Corpus created successfully: {corpus.name}")

    print(f"3. Importing file from GCS: {GCS_PATH}...")
    resp = rag.import_files(
        corpus_name=corpus.name,
        paths=[GCS_PATH],
        transformation_config=rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(chunk_size=512, chunk_overlap=100)
        ),
        llm_parser=rag.LlmParserConfig(
            model_name="gemini-2.5-flash",
            custom_parsing_prompt=PARSING_PROMPT,
        ),
    )
    print(f"   ✓ Imported {resp.imported_rag_files_count} file(s) into RAG corpus!")
    print(f"\nFULL_CORPUS_NAME={corpus.name}")
    return corpus.name


if __name__ == "__main__":
    create_and_index_rag_corpus()
