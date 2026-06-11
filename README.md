# LLM Wiki Knowledge System

An experimental personal knowledge-base system where an LLM maintains a persistent markdown wiki from uploaded source files.

Instead of only doing traditional RAG over raw documents, this project tries to build a compounding wiki layer. Uploaded files are summarized, indexed, stored as source pages, and used to update related wiki pages.

## What This Project Does

- Upload source files through a Streamlit UI.
- Extract text from `.txt`, `.md`, and `.pdf` files.
- Store document chunks as embeddings in Qdrant.
- Use an LLM to summarize uploaded sources.
- Extract entities and concepts.
- Create markdown wiki pages in `data/wiki/`.
- Maintain `index.md` and `log.md`.
- Search the accumulated wiki when answering questions.
- Keep ingestion and querying as separate workflows.

## Project Structure

```text
llm_wiki/
|-- AGENTS.md
|-- Dockerfile
|-- README.md
|-- docker-compose.yml
|-- requirements.txt
|-- setup_qdrant.py
|-- test.py
|-- backend/
|   |-- main.py
|   |-- graph/
|   |   `-- langgraph_app.py
|   `-- services/
|       |-- document_loader.py
|       |-- embedding.py
|       |-- entity_extractor.py
|       |-- llm_service.py
|       |-- qdrant_service.py
|       `-- wiki_manager.py
|-- data/
|   |-- raw/
|   `-- wiki/
|       |-- index.md
|       `-- log.md
`-- frontend/
    `-- app.py
```

## Architecture

The system has three main knowledge layers:

1. **Raw sources**
   - Uploaded documents.
   - Treated as source material.
   - Currently text is extracted and processed through the app.

2. **Vector store**
   - Qdrant stores embeddings for document chunks.
   - Used as supporting retrieval infrastructure.

3. **Markdown wiki**
   - Stored in `data/wiki/`.
   - The main persistent artifact.
   - Contains source summaries, concept pages, entity pages, open questions, contradictions, `index.md`, and `log.md`.

The operating conventions are documented in `AGENTS.md`.

## Workflows

### Ingest Workflow

When a file is uploaded:

1. Streamlit receives the file.
2. `document_loader.py` extracts text.
3. `langgraph_app.py` chunks the text.
4. `embedding.py` creates local embeddings.
5. `qdrant_service.py` stores chunks in Qdrant.
6. The LLM summarizes the uploaded source.
7. The LLM extracts entities/concepts.
8. A source summary page is created in `data/wiki/`.
9. The LLM plans wiki maintenance updates.
10. Concept/entity/synthesis pages are created or updated.
11. `index.md` and `log.md` are updated.

### Query Workflow

When a user asks a question:

1. The app searches existing markdown wiki pages.
2. If needed, it can use Qdrant vector search as supporting context.
3. Retrieved context is passed to the LLM.
4. The LLM answers only from the provided context.

Questions are not ingested as source pages.

## Supported Upload Formats

- `.txt`
- `.md`
- `.pdf`

PDF support uses `pypdf`, so it works best with PDFs that contain selectable text. Scanned image-only PDFs need OCR support, which is not implemented yet.

## Local Setup

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file:

```env
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_api_key
```

Initialize the Qdrant collection:

```powershell
python setup_qdrant.py
```

Run the Streamlit app:

```powershell
streamlit run frontend/app.py
```

## Docker (Local)

Build and run the app with Docker Compose:

```powershell
docker compose up --build
```

Then open:

```text
http://localhost:8501
```

The Compose setup starts:

- `app`: the Streamlit application

The `data/` directory is mounted into the container so generated wiki files persist on your machine.

For local Docker development, configure `.env` with your API keys and Qdrant credentials:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
GROQ_API_KEY=your_groq_api_key
QDRANT_URL=your_qdrant_cloud_url
QDRANT_API_KEY=your_qdrant_api_key
EMBEDDING_MODEL=your_embedding_model
```

## AWS EC2 Deployment

This guide covers deploying the LLM Wiki to AWS EC2 using Docker Compose.

### Prerequisites

- AWS Account with EC2 access
- Local SSH client (PowerShell on Windows, Terminal on macOS/Linux)
- GitHub repository URL
- API keys ready (OpenRouter, Groq, Qdrant)

### Part 1: Launch EC2 Instance

1. Go to **AWS Console** → **EC2** → **Launch Instance**
2. Configure:
   - **Name**: `llm-wiki`
   - **AMI**: Ubuntu (e.g., Ubuntu 22.04 LTS)
   - **Instance Type**: `t3.micro` or larger (free tier eligible)
   - **Key Pair**: Create or select existing `.pem` file (download if new)
3. **Network settings**: Enable HTTP (port 80) and Custom TCP (port 8501)
4. Launch the instance
5. Once running, note the **Public IPv4 Address** (e.g., `13.xx.xx.xx`)
   - **Important**: Use Public IPv4, NOT Private IPv4 (172.31.x.x)

### Part 2: Configure Security Group

Update the Security Group inbound rules:

| Type       | Port | Source    | Purpose          |
| ---------- | ---- | --------- | ---------------- |
| SSH        | 22   | Your IP   | Remote access    |
| Custom TCP | 8501 | 0.0.0.0/0 | Streamlit access |

**Troubleshooting**: If you get "Connection timed out" on SSH:
- Verify your current public IP matches the SSH rule
- Or temporarily set SSH source to `0.0.0.0/0` for testing only

### Part 3: Connect via SSH

#### Windows (PowerShell)

Navigate to your `.pem` file directory:

```powershell
cd Downloads
ssh -i llm_wiki.pem ubuntu@13.xx.xx.xx
```

#### macOS/Linux (Terminal)

```bash
ssh -i /path/to/llm_wiki.pem ubuntu@13.xx.xx.xx
```

On first connection, confirm:

```text
Are you sure you want to continue connecting? (yes/no) yes
```

### Part 4: Install Docker

Update package lists:

```bash
sudo apt update
```

Install Docker:

```bash
sudo apt install docker.io -y
```

Verify installation:

```bash
docker --version
```

Start Docker service:

```bash
sudo systemctl start docker
sudo systemctl status docker
```

Press `q` to exit status view.

**Grant Docker permissions** (avoid using `sudo` for every command):

```bash
sudo usermod -aG docker ubuntu
exit
```

Reconnect:

```powershell
ssh -i llm_wiki.pem ubuntu@13.xx.xx.xx
```

Verify Docker works without sudo:

```bash
docker ps
```

### Part 5: Install Git

Check if Git is installed:

```bash
git --version
```

If not, install:

```bash
sudo apt install git -y
```

### Part 6: Clone Project

Clone your repository:

```bash
git clone https://github.com/your-username/llm_wiki.git
cd llm_wiki
```

Verify:

```bash
ls
```

### Part 7: Create `.env` File

Create the environment file:

```bash
nano .env
```

Paste your configuration (replace with actual values):

```env
OPENROUTER_API_KEY=sk_or_xxxxxxxxxxxxxxxx
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
QDRANT_URL=https://your-qdrant-url:6333
QDRANT_API_KEY=xxxxxxxxxxxxxxxx
EMBEDDING_MODEL=mixedbread-ai/mxbai-embed-large
```

Save the file:

```text
Ctrl + O
Enter
Ctrl + X
```

Verify:

```bash
cat .env
```

### Part 8: Install Docker Compose

Check if installed:

```bash
docker-compose --version
```

If not available, install manually:

```bash
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker-compose --version
```

### Part 9: Verify docker-compose.yml

Ensure your `docker-compose.yml` uses cloud Qdrant (not local container):

```yaml
services:
  app:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

**Common Issue**: Old compose files may reference a local Qdrant container. Remove that service and use cloud Qdrant via `.env` instead.

Update locally and push if needed:

```bash
git add docker-compose.yml
git commit -m "Use cloud Qdrant instead of local container"
git push origin main
```

Pull on EC2:

```bash
git pull origin main
```

### Part 10: Build and Run Application

Inside the project directory:

```bash
cd ~/llm_wiki
docker-compose up --build
```

**First time**: Watch the logs to ensure build succeeds. This may take 2-5 minutes.

**On success**, stop the foreground process:

```text
Ctrl + C
```

Run in background (persistent):

```bash
docker-compose up -d
```

### Part 11: Verify Container is Running

Check running containers:

```bash
docker ps
```

Expected output:

```text
CONTAINER ID    IMAGE              STATUS          PORTS
abc123def456    llm_wiki-app-1     Up 2 minutes    0.0.0.0:8501->8501/tcp
```

### Part 12: Access the Application

Open your browser and navigate to:

```text
http://13.xx.xx.xx:8501
```

Replace `13.xx.xx.xx` with your EC2 instance's Public IPv4 Address.

The Streamlit UI should load.

### Part 13: View Application Logs

Check logs for errors:

```bash
docker logs -f llm_wiki-app-1
```

Or use container ID:

```bash
docker logs -f abc123def456
```

Useful for debugging:
- Upload failures
- API errors
- Connection issues to Qdrant

Press `Ctrl + C` to exit logs.

### Part 14: Access Files on EC2

List project files:

```bash
cd ~/llm_wiki
ls
```

List all files (including hidden):

```bash
ls -la
```

Recursive listing:

```bash
ls -R
```

### Part 15: Access Container Files

Enter running container:

```bash
docker exec -it llm_wiki-app-1 bash
```

Inside container, explore:

```bash
ls /app
ls /app/data
ls /app/data/wiki
```

Exit container:

```bash
exit
```

### Part 16: Manage Application

Stop the application:

```bash
docker stop llm_wiki-app-1
```

Start it again:

```bash
docker start llm_wiki-app-1
```

Restart:

```bash
docker restart llm_wiki-app-1
```

Stop and remove containers:

```bash
docker-compose down
```

### Part 17: Update Application

After code changes, pull and rebuild:

```bash
cd ~/llm_wiki
git add .
git commit -m "Your commit message"
git push origin main
```

On EC2:

```bash
cd ~/llm_wiki
git pull origin main
docker-compose down
docker-compose up -d --build
```

### Part 18: Important Notes

1. **Use Public IPv4 Address**: Do not use Private IPv4 (172.31.x.x)

2. **SSH Timeout**: Usually indicates Security Group misconfiguration. Update SSH inbound rule with your current public IP.

3. **.env Security**: Never commit `.env` to GitHub. Configure it locally on the instance.

4. **Container Persistence**: Docker containers keep running even if:
   - SSH session closes
   - PowerShell/Terminal window closes
   - Local machine shuts down
   - EC2 instance is stopped and restarted (with `restart: unless-stopped` policy)

5. **Check Logs**: Always use `docker logs -f llm_wiki-app-1` when diagnosing issues.

6. **Free Tier Limitations**: EC2 free tier instances (~1 GB RAM) may be slow for LLM/RAG workloads. Consider upgrading to `t3.small` or `t4g.small` for better performance.

7. **Data Persistence**: Wiki files in `./data/wiki/` persist on EC2 filesystem. Back up regularly or push to GitHub.

8. **Costs**: Monitor your AWS EC2 usage. Free tier covers 750 hours/month of `t2.micro`. Larger instances or data transfer incur charges.

## LLM Providers

LLM calls are handled in `backend/services/llm_service.py`.

Currently configured clients:

- Groq, using OpenAI-compatible API
- OpenRouter, using OpenAI-compatible API

The default generation path uses Groq:

```python
call_groq(prompt, model="llama-3.3-70b-versatile")
```

## Token Limit Note

Large files can exceed the LLM provider's token or rate limits if the entire extracted text is sent in one request.

This project currently keeps the workflow simple, but production usage should add:

- chunked summarization
- prompt/context budgeting
- retry/backoff for rate limits
- background ingestion queue for large documents

## Current Limitations

- Large PDFs may hit Groq token-per-minute limits.
- Scanned PDFs are not supported.
- Wiki maintenance quality depends on the LLM response.
- Contradiction detection is basic and prompt-driven.
- There is no dedicated lint/health-check workflow yet.
- No authentication or multi-user support.
- `backend/main.py` is currently empty; the app is Streamlit-first.

## Scope for Further Improvements

- Adding a "Lint Wiki" workflow.
- Adding OCR for scanned PDFs.
- Adding chunked summarization for large files.
- Adding a "Save this answer to wiki" button.
- Improve entity/concept page linking.
- Adding source metadata and YAML frontmatter.
- Adding better search over markdown pages.
- Adding tests around wiki updates and duplicate page handling.
- Multi-user authentication and access control.
- Automated wiki health checks and validation.

## Git Commit Do's and Don'ts

- Do not commit `.env`.
- Do not commit `venv/`.
- Consider committing `data/wiki/` if you want your generated wiki in version control.
- Consider committing only sample files under `data/` if the wiki contains private information.
