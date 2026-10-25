from typing import Dict, Any, List

VLM_EXTRACTION_PROMPT_TEMPLATE = """You are a forensic data auditor reviewing evidence for personal data deletion compliance.
Extract all customer identifiers, system references, resource IDs, and record statuses visible in this artifact.
Return a structured JSON with:
{
  "identifiers_found": ["..."],
  "system_id": "...",
  "resource_id": "...",
  "status": "...",
  "details": "..."
}
"""

def extract_from_file(file_path: str, file_type: str, file_id: str = "", case_id: str = "") -> Dict[str, Any]:
    """
    VLM client wrapper for unstructured visual/document files (PDF/images).
    Uses pypdf for text-based PDFs deterministically, with optional VLM multimodal API integration.
    """
    if file_type.lower() == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            extracted_text = "\n".join([page.extract_text() or "" for page in reader.pages])
            return {
                "success": True,
                "text": extracted_text,
                "pages": len(reader.pages)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "text": ""}
            
    elif file_type.lower() in ["png", "jpg", "jpeg"]:
        return {
            "success": False,
            "text": "",
            "identifiers_found": [],
            "error": "No image OCR backend is configured; artifact content was not inspected."
        }
        
    return {"success": False, "error": f"Unsupported file type: {file_type}"}

def test_vlm_client():
    from config import DATASET_DIR
    pdf_path = os.path.join(DATASET_DIR, "evidence/documents/delivery_correction_attachment.pdf")
    res = extract_from_file(pdf_path, "pdf", "evidence_58", "test_case")
    assert res["success"] is True
    assert "priya.raman@gmail.com" in res["text"]
    print("VLM client PDF extraction test passed successfully!")

if __name__ == "__main__":
    test_vlm_client()
