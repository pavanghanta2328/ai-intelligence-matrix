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
        Dynamically extracts unigrams, bigrams, and trigrams from any raw text,
        expanding synonyms dynamically via config/skill_synonyms.json.
        """
        if not text:
            return []
        
        raw_text = text.lower()
        cleaned = re.sub(r'[^a-z0-9\s\-\+\#\.]', ' ', raw_text)
        tokens = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
        
        extracted = set(tokens)
        # Dynamic n-gram generation (bigrams & trigrams)
        for i in range(len(tokens) - 1):
            extracted.add(f"{tokens[i]} {tokens[i+1]}")
        for i in range(len(tokens) - 2):
            extracted.add(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")

        # Dynamic synonym expansion from JSON configuration
        final_terms = set(extracted)
        for token in tokens:
            for canonical, aliases in self.synonyms.items():
                if token == canonical or token in aliases:
                    final_terms.add(canonical)
                    for a in aliases[:5]:
                        if len(a) > 2:
                            final_terms.add(a)

        return list(final_terms)

    def score_item(self, item, keywords):
        """
        Calculates mathematical match score purely algorithmically based on phrase overlap,
        n-gram length, and field location (Title > PageTitle > Description).
        """
        if not keywords:
            return 0.0, [], ""
        
        title = (item.get("Title") or "").lower()
        desc = (item.get("Description") or "").lower()
        p_title = (item.get("PageTitle") or "").lower()
        p_desc = (item.get("PageDescription") or "").lower()
        p_outline = " ".join(item.get("PageOutline") or []).lower()
        
        combined_text = f"{title} {desc} {p_title} {p_desc} {p_outline}"
        
        matched_kw = []
        score_points = 0.0
        max_possible = max(1, len(keywords)) * 25.0
        
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in combined_text:
                matched_kw.append(kw)
                
                # Dynamic math weighting based on n-gram length and field location
                words_in_kw = len(kw_lower.split())
                length_multiplier = 1.0 + (words_in_kw * 0.5)  # Multi-word phrase matches get higher weight
                
                if kw_lower in title:
                    score_points += 35.0 * length_multiplier
                elif kw_lower in p_title:
                    score_points += 25.0 * length_multiplier
                elif kw_lower in desc:
                    score_points += 15.0 * length_multiplier
                elif kw_lower in p_desc or kw_lower in p_outline:
                    score_points += 10.0 * length_multiplier
                else:
                    score_points += 5.0 * length_multiplier

        # Normalized mathematical ratio formula (0.0 - 100.0%)
        if max_possible > 0 and score_points > 0:
            raw_ratio = score_points / max_possible
            final_score = min(100.0, round(raw_ratio * 100.0, 1))
        else:
            final_score = 0.0
        
        # Sort matched keywords by phrase length (longest keyphrases first)
        sorted_matched = sorted(list(set(matched_kw)), key=lambda x: len(x), reverse=True)
        integration_tip = self.generate_role_tip(item, sorted_matched)
        
        return final_score, sorted_matched[:3], integration_tip

    def generate_role_tip(self, item, matched_keywords):
        """
        Generates dynamic integration & architecture guidance for any item type.
        """
        cat = item.get("Type", "")
        matched_str = ", ".join(matched_keywords[:3]) if matched_keywords else "architecture requirement"
        
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
        
        results = {}
        low_confidence_categories = []
        
        for category in ALL_12_CATEGORIES:
            cat_items = all_updates_dict.get(category, [])
            scored_items = []
            
            for item in cat_items:
                score, matched_kw, tip = self.score_item(item, keywords)
                if score > 0:
                    item_copy = dict(item)
                    item_copy["MatchScore"] = score
                    item_copy["MatchedKeywords"] = matched_kw
                    item_copy["IntegrationTip"] = tip
                    scored_items.append(item_copy)
                    
            scored_items.sort(key=lambda x: x["MatchScore"], reverse=True)
            top_matches = scored_items[:top_k]
            
            results[category] = top_matches
            
            # If category has fewer than 2 matches or low score, mark for live fallback execution
            if len(top_matches) < 2 or (top_matches and top_matches[0]["MatchScore"] < 25.0):
                low_confidence_categories.append(category)
                
        return {
            "scenario": scenario_text,
            "keywords": keywords,
            "recommendations": results,
            "low_confidence_categories": low_confidence_categories
        }

scenario_matcher = UniversalMultiRoleMatcher()
