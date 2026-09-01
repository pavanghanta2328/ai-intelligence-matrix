import re
import os
import json
import math

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALL_12_CATEGORIES = [
    "GitHub Repo",
    "Hugging Face Model",
    "Hugging Face Dataset",
    "arXiv Research Paper",
    "PyPI Release",
    "Corporate Blog",
    "Medium & Dev Community",
    "Reddit Discussion",
    "Product Hunt Launch",
    "AI Course",
    "YouTube Video",
    "Prompt & Guardrail Templates"
]

# Standard English & Filler Stopwords to ignore in technical keyword extraction
ENGLISH_STOPWORDS = {
    "we", "need", "to", "build", "building", "a", "an", "the", "and", "or", "for", "with",
    "in", "on", "at", "by", "from", "up", "about", "into", "over", "after",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "but", "if", "or", "because", "as", "until", "while",
    "of", "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from",
    "up", "down", "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "can", "will",
    "just", "don", "should", "now", "requirement", "requirements", "project",
    "system", "app", "application", "scenario", "solution", "tool", "tools",
    "working", "create", "using", "use", "case", "looking", "find", "provide",
    "list", "recommended", "recommendation", "recommendations", "required",
    "platform", "help", "this", "that", "our", "my", "your", "its", "it",
    "enterprise", "architecture", "infrastructure", "stack", "best", "top", "new",
    "thought", "think", "thinking", "wanted", "trying", "idea", "please", "way", "based"
}

def load_synonyms():
    synonyms_map = {}
    path = os.path.join(BASE_DIR, "config", "skill_synonyms.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for cat, items in data.items():
                    if isinstance(items, dict):
                        for canonical, aliases in items.items():
                            synonyms_map[canonical.lower()] = [a.lower() for a in aliases]
        except Exception as e:
            print(f"Error loading skill_synonyms.json: {e}")
    return synonyms_map

_SYNONYMS_CACHE = load_synonyms()

class UniversalMultiRoleMatcher:
    def __init__(self):
        self.synonyms = _SYNONYMS_CACHE

    def extract_keywords(self, text):
        """
        Extracts technical unigrams, bigrams, and trigrams from raw text,
        filtering out generic English stopwords to prevent low-relevance noise.
        """
        if not text:
            return []
        
        raw_text = text.lower()
        cleaned = re.sub(r'[^a-z0-9\s\-\+\#\.]', ' ', raw_text)
        raw_tokens = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
        
        # Meaningful tokens (excluding English stopwords)
        meaningful_unigrams = [w for w in raw_tokens if w not in ENGLISH_STOPWORDS and len(w) > 2]
        
        extracted = set(meaningful_unigrams)
        
        # Dynamic n-gram generation (bigrams & trigrams from meaningful sequences)
        for i in range(len(raw_tokens) - 1):
            w1, w2 = raw_tokens[i], raw_tokens[i+1]
            if w1 not in ENGLISH_STOPWORDS or w2 not in ENGLISH_STOPWORDS:
                if len(w1) > 1 and len(w2) > 1:
                    extracted.add(f"{w1} {w2}")
                    
        for i in range(len(raw_tokens) - 2):
            w1, w2, w3 = raw_tokens[i], raw_tokens[i+1], raw_tokens[i+2]
            if any(w not in ENGLISH_STOPWORDS for w in [w1, w2, w3]):
                extracted.add(f"{w1} {w2} {w3}")

        # Dynamic synonym expansion
        final_terms = set(extracted)
        for token in meaningful_unigrams:
            for canonical, aliases in self.synonyms.items():
                if token == canonical or token in aliases:
                    final_terms.add(canonical)
                    for a in aliases[:3]:
                        if len(a) > 2:
                            final_terms.add(a)

        return list(final_terms)

    def extract_subject_anchor(self, text):
        """
        Dynamically extracts the core technical Subject Anchor (the primary compound noun phrase)
        from raw prompt text without using any hardcoded domain lists.
        """
        if not text:
            return ""
        
        # Split text into natural language clauses
        clauses = re.split(r'[,;\.\n]| and | that | with | for ', text.lower())
        
        candidates = []
        for clause in clauses:
            words = [w.strip() for w in re.findall(r'\b[a-zA-Z0-9\-]+\b', clause) if w.strip() not in ENGLISH_STOPWORDS and len(w.strip()) > 2]
            if len(words) >= 2:
                candidates.append(" ".join(words[:3]))
            elif len(words) == 1:
                candidates.append(words[0])
                
        if candidates:
            # Prioritize compound technical phrases as the primary subject anchor
            candidates.sort(key=lambda x: (len(x.split()), len(x)), reverse=True)
            return candidates[0]
        return ""

    def score_item(self, item, keywords, subject_anchor=""):
        """
        Calculates mathematical match score based purely on technical term & keyphrase match,
        filtering out generic stopword noise and enforcing subject anchor alignment.
        """
        if not keywords:
            return 0.0, [], ""
        
        title = (item.get("Title") or "").lower()
        desc = (item.get("Description") or "").lower()
        p_title = (item.get("PageTitle") or "").lower()
        p_desc = (item.get("PageDescription") or "").lower()
        p_outline = " ".join(item.get("PageOutline") or []).lower()
        
        combined_text = f"{title} {desc} {p_title} {p_desc} {p_outline}"
        
        # Filter keywords to only technical terms (no stopwords)
        tech_keywords = [k for k in keywords if k not in ENGLISH_STOPWORDS]
        if not tech_keywords:
            tech_keywords = keywords
            
        matched_kw = []
        score_points = 0.0
        max_possible = max(1, len(tech_keywords)) * 25.0
        
        for kw in tech_keywords:
            kw_lower = kw.lower()
            if kw_lower in combined_text:
                matched_kw.append(kw)
                
                # Pure dynamic math weighting based on n-gram compound length (multi-word technical terms)
                words_in_kw = len(kw_lower.split())
                weight = 1.0 + (words_in_kw * 2.0)
                
                if kw_lower in title:
                    score_points += 35.0 * weight
                elif kw_lower in p_title:
                    score_points += 30.0 * weight
                elif kw_lower in desc:
                    score_points += 20.0 * weight
                elif kw_lower in p_desc or kw_lower in p_outline:
                    score_points += 10.0 * weight
                else:
                    score_points += 5.0 * weight

        # Subject Anchor Alignment Check (Subject Mismatch Penalty)
        if subject_anchor:
            anchor_words = [w for w in subject_anchor.split() if w not in ENGLISH_STOPWORDS]
            has_anchor = any(w in combined_text for w in anchor_words)
            if not has_anchor:
                # Heavy penalty if item completely misses the core subject anchor
                score_points *= 0.05
            else:
                score_points *= 1.5

        # Normalized mathematical ratio formula (0.0 - 100.0%)
        if max_possible > 0 and score_points > 0:
            raw_ratio = score_points / max_possible
            final_score = min(100.0, round(raw_ratio * 100.0, 1))
        else:
            final_score = 0.0
        
        # Sort matched keywords by length (longest keyphrases first, no stopwords)
        clean_matched = [k for k in matched_kw if k not in ENGLISH_STOPWORDS]
        sorted_matched = sorted(list(set(clean_matched or matched_kw)), key=lambda x: (len(x.split()), len(x)), reverse=True)
        integration_tip = self.generate_role_tip(item, sorted_matched)
        
        return final_score, sorted_matched[:3], integration_tip

    def generate_role_tip(self, item, matched_keywords):
        cat = item.get("Type", "")
        clean_kw = [k for k in matched_keywords if k not in ENGLISH_STOPWORDS]
        matched_str = ", ".join(clean_kw[:3]) if clean_kw else "architecture requirement"
        
        if cat == "GitHub Repo":
            return f"Clone and integrate modular repository components for [{matched_str}]."
        elif cat in ["PyPI Release", "Multi-Ecosystem Packages"]:
            return f"Add SDK / package dependency to service stack to implement [{matched_str}]."
        elif cat == "Hugging Face Model":
            return f"Download model weights or deploy containerized inference endpoint for [{matched_str}]."
        elif cat == "Hugging Face Dataset":
            return f"Integrate dataset for model fine-tuning, benchmark evaluation, or ground-truth validation for [{matched_str}]."
        elif cat == "arXiv Research Paper":
            return f"Review foundational research paper, mathematical formulation, and architecture specifications for [{matched_str}]."
        elif cat in ["Corporate Blog", "Medium & Dev Community"]:
            return f"Read real-world production engineering guide and implementation benchmarks for [{matched_str}]."
        elif cat == "Prompt & Guardrail Templates":
            return f"Import production system prompt rubrics, safety guardrails, and structured JSON schema specs for [{matched_str}]."
        elif cat == "AI Course":
            return f"Complete practical hands-on course modules covering architecture patterns for [{matched_str}]."
        elif cat == "YouTube Video":
            return f"Watch step-by-step technical implementation walkthrough and live demo for [{matched_str}]."
        else:
            return f"Actionable developer reference resource for [{matched_str}]."

    def match_scenario(self, scenario_text, all_updates_dict, top_k=5):
        keywords = self.extract_keywords(scenario_text)
        subject_anchor = self.extract_subject_anchor(scenario_text)
        
        results = {}
        low_confidence_categories = []
        
        for category in ALL_12_CATEGORIES:
            cat_items = all_updates_dict.get(category, [])
            scored_items = []
            
            for item in cat_items:
                score, matched_kw, tip = self.score_item(item, keywords, subject_anchor)
                # Only include items that meet the minimum relevance threshold (>= 15.0%)
                if score >= 15.0:
                    item_copy = dict(item)
                    item_copy["MatchScore"] = score
                    item_copy["MatchedKeywords"] = matched_kw
                    item_copy["IntegrationTip"] = tip
                    scored_items.append(item_copy)
                    
            scored_items.sort(key=lambda x: x["MatchScore"], reverse=True)
            top_matches = scored_items[:top_k]
            
            results[category] = top_matches
            
            # If category has fewer than 2 matches or low score, mark for live fallback execution
            if len(top_matches) < 2 or (top_matches and top_matches[0]["MatchScore"] < 20.0):
                low_confidence_categories.append(category)
                
        return {
            "scenario": scenario_text,
            "keywords": keywords,
            "subject_anchor": subject_anchor,
            "recommendations": results,
            "low_confidence_categories": low_confidence_categories
        }

scenario_matcher = UniversalMultiRoleMatcher()
