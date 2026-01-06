"""Demo of LLM integration with cost tracking."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm import LLMClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_llm_calls():
    """Demonstrate LLM calls with various models and prompts."""
    logger.info("=" * 70)
    logger.info("LLM Integration Demo")
    logger.info("=" * 70)
    
    # Create LLM client
    llm = LLMClient(default_model="gpt-4o-mini")
    
    # Test 1: Simple prompt
    logger.info("\n🤖 Test 1: Simple prompt...")
    try:
        response, metadata = await llm.simple_prompt(
            prompt="What are the key benefits of fault-tolerant systems?",
            system="You are a technical expert in distributed systems.",
            max_tokens=200,
        )
        
        logger.info(f"✅ Response: {response[:150]}...")
        logger.info(f"   Model: {metadata.model}")
        logger.info(f"   Tokens: {metadata.total_tokens}")
        logger.info(f"   Cost: ${metadata.cost_usd:.6f}")
        logger.info(f"   Latency: {metadata.latency_ms:.0f}ms")
    
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
    
    # Test 2: Multi-turn conversation
    logger.info("\n💬 Test 2: Multi-turn conversation...")
    try:
        messages = [
            {"role": "system", "content": "You are a helpful Python expert."},
            {"role": "user", "content": "What is asyncio used for?"},
        ]
        
        response, metadata = await llm.chat_completion(messages, max_tokens=150)
        
        logger.info(f"✅ Response: {response[:150]}...")
        logger.info(f"   Cost: ${metadata.cost_usd:.6f}")
        
        # Continue conversation
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": "Give me a simple example."})
        
        response2, metadata2 = await llm.chat_completion(messages, max_tokens=200)
        
        logger.info(f"✅ Follow-up: {response2[:150]}...")
        logger.info(f"   Total cost: ${metadata.cost_usd + metadata2.cost_usd:.6f}")
    
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
    
    # Test 3: Compare models
    logger.info("\n📊 Test 3: Compare different models...")
    
    prompt = "Explain checkpointing in 50 words."
    models = ["gpt-4o-mini", "gpt-3.5-turbo"]
    
    for model in models:
        try:
            response, metadata = await llm.simple_prompt(
                prompt=prompt,
                model=model,
                max_tokens=100,
            )
            
            logger.info(f"✅ {model}:")
            logger.info(f"   Response: {response[:100]}...")
            logger.info(f"   Tokens: {metadata.total_tokens}, Cost: ${metadata.cost_usd:.6f}")
        
        except Exception as e:
            logger.error(f"❌ {model} failed: {e}")
    
    # Test 4: Embeddings
    logger.info("\n🔢 Test 4: Generate embeddings...")
    try:
        texts = [
            "Distributed systems require fault tolerance.",
            "Checkpointing enables recovery from failures.",
            "Redis is an in-memory data store.",
        ]
        
        embeddings, metadata = await llm.embeddings(texts)
        
        logger.info(f"✅ Generated {len(embeddings)} embeddings")
        logger.info(f"   Dimensions: {len(embeddings[0])}")
        logger.info(f"   Cost: ${metadata.cost_usd:.6f}")
    
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
    
    logger.info("\n" + "=" * 70)
    logger.info("🎉 LLM Demo completed!")
    logger.info("=" * 70)


async def demo_task_simulation():
    """Simulate a task with LLM calls similar to worker execution."""
    logger.info("=" * 70)
    logger.info("Task Simulation with LLM")
    logger.info("=" * 70)
    
    llm = LLMClient()
    total_cost = 0.0
    
    # Simulate search node
    logger.info("\n🔍 Node 1: Search...")
    try:
        response, metadata = await llm.simple_prompt(
            prompt="Find information about Redis persistence mechanisms.",
            system="You are a research assistant.",
            max_tokens=200,
        )
        
        logger.info(f"✅ Search result: {response[:100]}...")
        logger.info(f"   Cost: ${metadata.cost_usd:.6f}")
        total_cost += metadata.cost_usd
    
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
    
    # Simulate analyze node
    logger.info("\n📊 Node 2: Analyze...")
    try:
        response, metadata = await llm.simple_prompt(
            prompt=f"Analyze this information and identify key points:\n\n{response}",
            system="You are an analytical assistant.",
            max_tokens=200,
        )
        
        logger.info(f"✅ Analysis: {response[:100]}...")
        logger.info(f"   Cost: ${metadata.cost_usd:.6f}")
        total_cost += metadata.cost_usd
    
    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
    
    # Simulate summarize node
    logger.info("\n📝 Node 3: Summarize...")
    try:
        response, metadata = await llm.simple_prompt(
            prompt=f"Create a concise summary:\n\n{response}",
            system="You are a summarization assistant.",
            max_tokens=100,
        )
        
        logger.info(f"✅ Summary: {response}")
        logger.info(f"   Cost: ${metadata.cost_usd:.6f}")
        total_cost += metadata.cost_usd
    
    except Exception as e:
        logger.error(f"❌ Summarization failed: {e}")
    
    logger.info(f"\n💰 Total task cost: ${total_cost:.6f}")
    logger.info("=" * 70)


if __name__ == "__main__":
    import os
    
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("❌ OPENAI_API_KEY environment variable not set!")
        logger.info("   Set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)
    
    if len(sys.argv) > 1 and sys.argv[1] == "task":
        # Run task simulation
        asyncio.run(demo_task_simulation())
    else:
        # Run basic LLM demo
        asyncio.run(demo_llm_calls())
