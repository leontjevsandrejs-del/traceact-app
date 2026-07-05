import glob
import os

from google import genai
from pypdf import PdfReader

def get_knowledge_base_text():
    kb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'knowledge_base')
    kb_text = ""
    if os.path.exists(kb_path):
        # Read txt files
        for filepath in glob.glob(os.path.join(kb_path, '*.txt')):
            with open(filepath, 'r', encoding='utf-8') as f:
                kb_text += f"\n--- {os.path.basename(filepath)} ---\n"
                kb_text += f.read()
        
        # Read pdf files
        for filepath in glob.glob(os.path.join(kb_path, '*.pdf')):
            try:
                reader = PdfReader(filepath)
                kb_text += f"\n--- {os.path.basename(filepath)} ---\n"
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        kb_text += text + "\n"
            except Exception as e:
                kb_text += f"\n[Error reading PDF {os.path.basename(filepath)}: {str(e)}]\n"
    return kb_text

def run_audit(client: genai.Client, model_name: str, manual_triage_data, evidence_text):
    if client is None:
        return "Error: Gemini API key is missing."

    kb_context = get_knowledge_base_text()
    
    prompt = f"""You are an elite, risk-adverse corporate auditor specializing in European technology regulations.

Here is the reference knowledge base (EU AI Act context):
{kb_context}

Here is the manual triage data provided by the user:
{manual_triage_data}

Here is the system architecture and data governance evidence uploaded by the user:
{evidence_text}

Your single task is to analyze the text descriptions of the corporate software project and look for compliance gaps.
You must:
1. Determine if the project falls under Prohibited, High-Risk, or Limited Risk.
2. Cite the exact section of the law that applies.
3. List any missing items (e.g., lack of human oversight, missing bias checks, missing documentation) in a clean bulleted list labeled 'Action Required'.

Output format:
### Classification: [Prohibited Risk / High-Risk / Limited Risk]

### Citation
[Citation here]

### Action Required
*   [Action 1]
*   [Action 2]
"""
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        try:
            available_models = [m.name for m in client.models.list()]
            models_str = "\n".join([f"- `{m}`" for m in available_models])
            return (
                f"An error occurred during the audit: {str(e)}\n\n"
                f"### Debug Info: Available models for your API key:\n{models_str}\n\n"
                f"Please update GEMINI_MODEL in `app.py` to one of the above."
            )
        except Exception as list_err:
            return f"An error occurred during the audit: {str(e)}\n\n(Failed to list models: {str(list_err)})"

