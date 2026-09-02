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
    "just", "don", "should", "now", "working", "use", "case", "looking", "find",
    "this", "that", "our", "my", "your", "its", "it", "wanted", "trying", "idea", "please", "way"
}

ACTION_VERB_STOPLIST = {
    "build", "building", "create", "creating", "design", "designing",
    "implement", "implementing", "develop", "developing", "make", "making",
    "construct", "constructing", "want", "need", "help", "thought", "think",
    "looking", "find", "provide", "run", "running", "set", "setting"
}

GENERIC_CONTAINER_NOUNS = {
    "system", "systems", "pipeline", "pipelines", "engine", "engines",
    "platform", "platforms", "framework", "frameworks", "tool", "tools",
    "service", "services", "application", "applications", "solution", "solutions"
}

def clean_technical_tokens(words, filter_container_nouns=True):
    cleaned = []
    for w in words:
        w_lower = w.strip().lower()
        if len(w_lower) <= 2:
            continue
        if w_lower in ENGLISH_STOPWORDS or w_lower in ACTION_VERB_STOPLIST:
            continue
        if filter_container_nouns and w_lower in GENERIC_CONTAINER_NOUNS:
            continue
        cleaned.append(w_lower)
    return cleaned

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
        Extracts unigrams, bigrams, and trigrams strictly WITHIN each natural clause boundary,
        preventing cross-clause junk bigrams (e.g. 'safety assigns', 'solvers based').
        """
        if not text:
            return []
        
        # Split text into natural clauses at expanded conjunctions & prepositions
        clauses = re.split(r'[,;\.\n]| and | that | with | for | to | by | from | of | based on | based upon | using | via | through | in order to ', text.lower())
        
        extracted = set()
        
        for clause in clauses:
            raw_tokens = re.findall(r'\b[a-zA-Z0-9\-]+\b', clause)
            clause_tokens = clean_technical_tokens(raw_tokens, filter_container_nouns=True)
            
            # Add clean unigrams from this clause
            for token in clause_tokens:
                extracted.add(token)
                
            # Dynamic N-gram generation strictly WITHIN this clause
            for i in range(len(clause_tokens) - 1):
                extracted.add(f"{clause_tokens[i]} {clause_tokens[i+1]}")
                
            for i in range(len(clause_tokens) - 2):
                extracted.add(f"{clause_tokens[i]} {clause_tokens[i+1]} {clause_tokens[i+2]}")

        return list(extracted)

    def score_anchor_candidate(self, candidate):
        """
        Scores candidate phrases to prioritize core technical domain subjects (multi-word compounds,
        hyphenated terms) over generic preamble phrases or single-word fragments.
        """
        cand_lower = candidate.lower()
        
        # Clean leading action verbs if present (e.g. 'evaluates multi-agent' -> 'multi-agent')
        words = [w for w in cand_lower.split() if w not in ACTION_VERB_STOPLIST and w not in {"evaluates", "assigns", "benchmarks", "validates"}]
        cand_clean = " ".join(words)
        
        # Multi-word compound length score (25.0 points per word)
        score = len(words) * 25.0
        
        # Hyphen bonus acts as a tiebreaker (+10.0), NOT an override that beats longer multi-word phrases
        if "-" in cand_clean:
            score += 10.0
            
        # Heavy penalty for generic preamble words
        preamble_words = {"ai-driven", "data science", "general", "basic", "simple", "standard", "custom", "overview"}
        for pw in preamble_words:
            if pw in cand_clean:
                score -= 40.0
                
        return score

    def extract_subject_anchor(self, text):
        """
        Extracts the highest-scoring technical Subject Anchor across all clauses in the prompt,
        skipping generic preamble clauses.
        """
        if not text:
            return ""
        
        # Expanded clause boundary delimiters including prepositions (to, for, by, from, of)
        clauses = re.split(r'[,;\.\n]| and | that | with | for | to | by | from | of | based on | based upon | using | via | through | in order to ', text.lower())
        candidates = []
        
        for clause in clauses:
            raw_words = re.findall(r'\b[a-zA-Z0-9\-]+\b', clause)
            all_words = clean_technical_tokens(raw_words, filter_container_nouns=False)
            cleaned_words = clean_technical_tokens(raw_words, filter_container_nouns=True)
            
            # Clean action verbs from candidate anchor
            cleaned_words_no_verbs = [w for w in cleaned_words if w not in {"evaluates", "assigns", "benchmarks", "validates"}]
            
            if len(cleaned_words_no_verbs) >= 2:
                candidates.append(" ".join(cleaned_words_no_verbs[:3]))
            elif len(cleaned_words) >= 2:
                candidates.append(" ".join(cleaned_words[:3]))
            elif len(all_words) >= 1:
                candidates.append(" ".join(all_words[:2]))
                
        if candidates:
            # Score all candidates across the prompt and select the highest-scoring technical anchor
            candidates.sort(key=lambda x: (self.score_anchor_candidate(x), len(x.split()), len(x)), reverse=True)
            return candidates[0]
        return ""

    def get_anchor_synonyms(self, anchor):
        """
        Dynamically generates canonical spelling variants & hyphen variations for any anchor
        without any hardcoded domain terms.
        """
        if not anchor:
            return []
        anchor_clean = anchor.lower().strip()
        syns = {anchor_clean}
        
        # 1. Hyphen & Space variations (e.g. multi-agent -> multiagent -> multi agent)
        no_hyphen = anchor_clean.replace("-", "")
        with_spaces = anchor_clean.replace("-", " ")
        syns.add(no_hyphen)
        syns.add(with_spaces)
        
        # 2. Compound bigrams/trigrams & hyphenated technical terms from anchor
        words = [w for w in re.findall(r'\b[a-zA-Z0-9\-]+\b', anchor_clean) if w not in ENGLISH_STOPWORDS and len(w) > 2]
        for w in words:
            if "-" in w:
                syns.add(w)
                syns.add(w.replace("-", ""))
                syns.add(w.replace("-", " "))
                
        for i in range(len(words) - 1):
            syns.add(f"{words[i]} {words[i+1]}")
            syns.add(f"{words[i]}-{words[i+1]}")
            syns.add(f"{words[i]}{words[i+1]}")
            
        # 3. Canonical aliases from skill_synonyms.json if available
        for token in words:
            for canonical, aliases in self.synonyms.items():
                if token == canonical or token in aliases:
                    syns.add(canonical)
                    syns.update(aliases[:3])
                    
        return list(syns)

    def classify_item_tier(self, item, keywords, subject_anchor=""):
        """
        Dynamically classifies each candidate item into Tier 1 (Domain Framework) or Tier 2 (Subsystem Tooling)
        purely by comparing candidate text against the prompt's Subject Anchor vs Subsystem Keyphrases.
        Zero hardcoded word sets!
        """
        title = (item.get("Title") or "").lower()
        desc = (item.get("Description") or "").lower()
        text = f"{title} {desc}"
        
        # Dynamic Domain Vocabulary derived from prompt Subject Anchor
        anchor_words = self.get_anchor_synonyms(subject_anchor) if subject_anchor else []
        has_domain = any(w in text for w in anchor_words if len(w) > 2)
        
        # Dynamic Utility Vocabulary derived from prompt Subsystem Keyphrases (non-anchor keyphrases)
        tech_keywords = [k.lower() for k in keywords if k not in ENGLISH_STOPWORDS]
        subsystem_terms = [k for k in tech_keywords if k not in anchor_words and len(k) > 2]
        has_utility = any(term in text for term in subsystem_terms)
        
        # Dynamic Tie-Break & Fallthrough Logic
        if has_domain and has_utility:
            classification = "Tier2"
            reason = "Tie-Break: Matched both prompt subject anchor and subsystem modifiers -> Assigned Tier 2 Subsystem Tooling Profile"
        elif has_utility:
            classification = "Tier2"
            reason = "Matched prompt subsystem modifiers -> Assigned Tier 2 Subsystem Tooling Profile"
        elif has_domain:
            classification = "Tier1"
            reason = "Matched prompt subject anchor -> Assigned Tier 1 Domain Framework Profile"
        else:
            classification = "Tier1"
            reason = "Default Fallthrough: Matched general vocabulary -> Defaulted to Tier 1 Domain Framework Profile"
            
        return classification, reason

    def score_item(self, item, keywords, subject_anchor=""):
        """
        Calculates mathematical match score using Calibrated Two-Tier Weighted Overlap:
        Tier 1: Score = 0.40 * S_anchor + 0.45 * S_keyphrases + 0.15 * S_unigrams
        Tier 2: Score = 0.15 * S_anchor + 0.60 * S_keyphrases + 0.25 * S_unigrams
        """
        if not keywords:
            return 0.0, [], ""
        
        title = (item.get("Title") or "").lower()
        desc = (item.get("Description") or "").lower()
        p_title = (item.get("PageTitle") or "").lower()
        p_desc = (item.get("PageDescription") or "").lower()
        p_outline = " ".join(item.get("PageOutline") or []).lower()
        
        combined_text = f"{title} {desc} {p_title} {p_desc} {p_outline}"
        
        # Classify Tier dynamically based on prompt terms
        tier, reason = self.classify_item_tier(item, keywords, subject_anchor)
        if tier == "Tier2":
            w_anchor, w_keyphrase, w_unigram = 0.15, 0.60, 0.25
        else:
            w_anchor, w_keyphrase, w_unigram = 0.40, 0.45, 0.15

        # 1. Subject Anchor Alignment Score (S_anchor)
        s_anchor = 0.0
        if subject_anchor:
            anchor_syns = self.get_anchor_synonyms(subject_anchor)
            if any(syn in combined_text for syn in anchor_syns):
                s_anchor = 100.0
            else:
                s_anchor = 0.0
        else:
            s_anchor = 100.0

        # 2. Keyphrase Overlap Score (S_keyphrases - Multi-word N-Grams)
        tech_keywords = [k for k in keywords if k not in ENGLISH_STOPWORDS]
        keyphrases = [k for k in tech_keywords if len(k.split()) > 1]
        unigrams = [k for k in tech_keywords if len(k.split()) == 1]
        
        matched_kw = []
        
        # Keyphrase scoring
        matched_kp_count = 0
        for kp in keyphrases:
            kp_lower = kp.lower()
            if kp_lower in combined_text:
                matched_kw.append(kp)
                matched_kp_count += 1
            else:
                # Keyphrase Synonym expansion check
                for canonical, aliases in self.synonyms.items():
                    if (kp_lower == canonical or kp_lower in aliases) and any(a in combined_text for a in aliases):
                        matched_kw.append(kp)
                        matched_kp_count += 1
                        break
                        
        s_keyphrase = (matched_kp_count / max(1, len(keyphrases))) * 100.0 if keyphrases else 0.0

        # 3. Unigram Coverage Score (S_unigrams)
        matched_uni_count = 0
        for uni in unigrams:
            uni_lower = uni.lower()
            if uni_lower in combined_text:
                matched_kw.append(uni)
                matched_uni_count += 1
        
        s_unigram = (matched_uni_count / max(1, len(unigrams))) * 100.0 if unigrams else 0.0

        # Final Calibrated Score Formula
        final_score = (w_anchor * s_anchor) + (w_keyphrase * s_keyphrase) + (w_unigram * s_unigram)
        final_score = min(100.0, round(final_score, 1))

        # Sort matched keywords by length (longest keyphrases first)
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
            
            # Deterministic pre-sorting by unique URL/Link to prevent thread-race ordering variance
            cat_items = sorted(cat_items, key=lambda x: str(x.get("Link", "")))
            
            scored_items = []
            for item in cat_items:
                score, matched_kw, tip = self.score_item(item, keywords, subject_anchor)
                # Enforce strict 25.0% relevance threshold
                if score >= 25.0:
                    item_copy = dict(item)
                    item_copy["MatchScore"] = score
                    item_copy["MatchedKeywords"] = matched_kw
                    item_copy["IntegrationTip"] = tip
                    scored_items.append(item_copy)
                    
            scored_items.sort(key=lambda x: (x["MatchScore"], str(x.get("Link", ""))), reverse=True)
            top_matches = scored_items[:top_k]
            
            results[category] = top_matches
            
            if len(top_matches) < 2 or (top_matches and top_matches[0]["MatchScore"] < 25.0):
                low_confidence_categories.append(category)
                
        return {
            "scenario": scenario_text,
            "keywords": keywords,
            "subject_anchor": subject_anchor,
            "recommendations": results,
            "low_confidence_categories": low_confidence_categories
        }

scenario_matcher = UniversalMultiRoleMatcher()
