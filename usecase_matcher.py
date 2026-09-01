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
        if not text:
            return []
        
        raw_text = text.lower()
        cleaned = re.sub(r'[^a-z0-9\s\-\+\#\.]', ' ', raw_text)
        tokens = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
        
        # Dynamic n-gram extraction (unigrams, bigrams, trigrams)
        extracted = set(tokens)
        for i in range(len(tokens) - 1):
            extracted.add(f"{tokens[i]} {tokens[i+1]}")
        for i in range(len(tokens) - 2):
            extracted.add(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")

        # Expand synonyms dynamically using loaded skill synonyms map
        final_keywords = set(extracted)
        for token in tokens:
            for canonical, aliases in self.synonyms.items():
                if token == canonical or token in aliases:
                    final_keywords.add(canonical)
                    for a in aliases[:5]:
                        if len(a) > 2:
                            final_keywords.add(a)

        return [k for k in final_keywords if len(k) > 1]

    def score_item(self, item, keywords):
        if not keywords:
            return 0.0, [], ""
        
        title = (item.get("Title") or "").lower()
        desc = (item.get("Description") or "").lower()
        p_title = (item.get("PageTitle") or "").lower()
        p_desc = (item.get("PageDescription") or "").lower()
        p_outline = " ".join(item.get("PageOutline") or []).lower()
        
        combined_text = f"{title} {desc} {p_title} {p_desc} {p_outline}"
        
        matched_kw = []
        weighted_score = 0.0
        max_possible = len(keywords) * 35.0  # Max potential match weight
        
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in combined_text:
                matched_kw.append(kw)
                
                # Dynamic TF/field weighting formula
                if kw_lower in title:
                    weighted_score += 35.0
                elif kw_lower in p_title:
                    weighted_score += 25.0
                elif kw_lower in desc:
                    weighted_score += 15.0
                elif kw_lower in p_desc:
                    weighted_score += 10.0
                else:
                    weighted_score += 5.0

        # Mathematical similarity score formula (Normalized 0.0 - 100.0%)
        if max_possible > 0:
            raw_ratio = weighted_score / (len(keywords) * 15.0)
            final_score = min(100.0, round(raw_ratio * 100.0, 1))
        else:
            final_score = 0.0
        
        integration_tip = self.generate_role_tip(item, matched_kw)
        return final_score, list(set(matched_kw)), integration_tip

    def generate_role_tip(self, item, matched_keywords):
        cat = item.get("Type", "")
        matched_str = ", ".join(matched_keywords[:3]) if matched_keywords else "general architecture patterns"
        
        if cat == "GitHub Repo":
            return f"Clone and integrate repository modules for [{matched_str}]."
        elif cat in ["PyPI Release", "Multi-Ecosystem Packages"]:
            return f"Install SDK / package dependency for direct integration of [{matched_str}]."
        elif cat == "Hugging Face Model":
            return f"Download model weights or deploy serving container for [{matched_str}]."
        elif cat == "Hugging Face Dataset":
            return f"Use dataset for fine-tuning, training, or evaluation of [{matched_str}]."
        elif cat == "arXiv Research Paper":
            return f"Review foundational paper & architecture specifications for [{matched_str}]."
        elif cat in ["Corporate Blog", "Medium & Dev Community"]:
            return f"Read real-world production engineering guide for [{matched_str}]."
        elif cat == "Prompt & Guardrail Templates":
            return f"Import production system prompts and safety rubrics for [{matched_str}]."
        else:
            return f"Useful developer reference resource for [{matched_str}]."

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
            
            if len(top_matches) < 2 or (top_matches and top_matches[0]["MatchScore"] < 20.0):
                low_confidence_categories.append(category)
                
        return {
            "scenario": scenario_text,
            "keywords": keywords,
            "recommendations": results,
            "low_confidence_categories": low_confidence_categories
        }

scenario_matcher = UniversalMultiRoleMatcher()
