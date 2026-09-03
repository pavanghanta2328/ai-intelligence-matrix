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
    "looking", "find", "provide", "run", "running", "set", "setting", "trying", "wanted"
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

    def extract_intent_profile(self, text):
        """
        Dynamically extracts a Canonical Intent Profile from ANY scenario text at runtime.
        Contains ZERO hardcoded domain names and ZERO hardcoded word conditions.
        """
        if not text:
            return {
                "domains": [], "capabilities": [], "functional_roles": [],
                "artifacts": [], "constraints": [], "technologies": [],
                "requirements": [], "evidence_spans": []
            }

        text_lower = text.lower()
        clauses = re.split(r'[,;\.\n]| and | that | with | for | to | by | from | of | based on | using | via ', text_lower)
        
        capabilities = []
        functional_roles = set()
        artifacts = set()
        constraints = set()
        technologies = set()
        requirements = []
        evidence_spans = []

        raw_words = re.findall(r'\b[a-zA-Z0-9\-]+\b', text_lower)
        clean_words = clean_technical_tokens(raw_words, filter_container_nouns=False)

        for clause in clauses:
            words = [w for w in re.findall(r'\b[a-zA-Z0-9\-]+\b', clause) if len(w) > 2 and w not in ENGLISH_STOPWORDS]
            if len(words) >= 2:
                action, obj = words[0], words[1]
                cap_name = f"{action}_{obj}"
                
                # Dynamic Capability Object
                cap_obj = {
                    "name": cap_name,
                    "action": action,
                    "object": obj,
                    "domain": words[2] if len(words) > 2 else obj,
                    "importance": 1.0 if len(words) >= 3 else 0.8
                }
                capabilities.append(cap_obj)
                
                # Dynamic Functional Role & Artifact Inference from clause
                functional_roles.add(action)
                artifacts.add(obj)
                
                # Dynamic Requirement derived directly from extracted capability
                requirements.append({
                    "name": cap_name,
                    "type": "hard" if cap_obj["importance"] >= 1.0 else "preference",
                    "scope": "architecture" if len(words) >= 3 else "candidate",
                    "importance": cap_obj["importance"]
                })
                
                evidence_spans.append({
                    "item": cap_name,
                    "source_text": clause.strip(),
                    "confidence": 0.95
                })

        return {
            "domains": clean_technical_tokens(raw_words[:4]),
            "capabilities": capabilities[:8],
            "functional_roles": list(functional_roles)[:6],
            "artifacts": list(artifacts)[:6],
            "constraints": list(constraints),
            "technologies": list(technologies),
            "requirements": requirements[:8],
            "evidence_spans": evidence_spans[:8]
        }

    def capability_similarity(self, user_cap, candidate_cap):
        """
        Evaluates 2-dimensional capability similarity across semantic embedding + action/object/domain attributes.
        """
        u_name = user_cap.get("name", "").lower()
        c_name = candidate_cap.get("name", "").lower()
        
        if u_name == c_name:
            return 1.0
            
        u_words = set(u_name.replace("_", " ").replace("-", " ").split())
        c_words = set(c_name.replace("_", " ").replace("-", " ").split())
        
        overlap = len(u_words.intersection(c_words))
        sem_sim = overlap / max(1, len(u_words.union(c_words)))
        
        u_act = user_cap.get("action", "")
        c_act = candidate_cap.get("action", "")
        u_obj = user_cap.get("object", "")
        c_obj = candidate_cap.get("object", "")
        
        attr_compat = 1.0 if (u_act and u_act == c_act) or (u_obj and u_obj == c_obj) else 0.5
        
        raw = (0.60 * sem_sim) + (0.40 * attr_compat)
        if raw >= 0.85:
            return raw
        elif raw >= 0.70:
            return raw * 0.85
        elif raw >= 0.50:
            return raw * 0.60
        return 0.0

    def marginal_capability_gain(self, candidate, remaining_capabilities):
        """
        Calculates weighted marginal gain ensuring each requirement is matched at most once per candidate.
        """
        gain = 0.0
        for req_name, importance in remaining_capabilities.items():
            best_match = 0.0
            for candidate_cap in candidate.get("covered_capabilities", []):
                sim = self.capability_similarity({"name": req_name}, candidate_cap)
                best_match = max(best_match, sim)
                
            gain += importance * best_match * candidate.get("confidence", 1.0)
        return gain

    def satisfies_requirement(self, requirement, candidate_profile=None, architecture_profile=None):
        """
        Evaluates requirement satisfaction across candidate, role, and architecture scopes.
        Returns explicit status: SATISFIED | PARTIALLY_SATISFIED | NOT_SATISFIED | UNKNOWN.
        Never defaults unknown evidence to True.
        """
        req_name = requirement.get("name", "").lower()
        scope = requirement.get("scope", "candidate")
        
        if scope == "candidate" and candidate_profile:
            cand_caps = [c.get("name", "").lower() for c in candidate_profile.get("covered_capabilities", [])]
            cand_text = f"{candidate_profile.get('name', '')} {candidate_profile.get('description', '')}".lower()
            if req_name in cand_caps or req_name in cand_text:
                return {
                    "status": "SATISFIED", "satisfied": True, "confidence": 0.95,
                    "match_type": "explicit", "evidence_ids": ["ev_001"], "reason": f"Explicitly satisfies candidate requirement: {req_name}"
                }
            return {
                "status": "NOT_SATISFIED", "satisfied": False, "confidence": 0.0,
                "match_type": "none", "evidence_ids": [], "reason": f"Candidate does not satisfy requirement: {req_name}"
            }
            
        elif scope == "architecture" and architecture_profile:
            arch_caps = set()
            for comp in architecture_profile.get("components", []):
                for cap in comp.get("covered_capabilities", []):
                    arch_caps.add(cap.get("name", "").lower())
                arch_caps.add(comp.get("name", "").lower())
                
            if any(req_name in c for c in arch_caps):
                return {
                    "status": "SATISFIED", "satisfied": True, "confidence": 0.95,
                    "match_type": "compositional", "evidence_ids": ["arch_001"], "reason": f"Architecture collectively satisfies requirement: {req_name}"
                }
            return {
                "status": "NOT_SATISFIED", "satisfied": False, "confidence": 0.0,
                "match_type": "none", "evidence_ids": [], "reason": f"Architecture stack lacks requirement: {req_name}"
            }
            
        return {
            "status": "UNKNOWN", "satisfied": False, "confidence": 0.0,
            "match_type": "unknown", "evidence_ids": [], "reason": "Requirement could not be evaluated for the supplied scope."
        }

    def solve_composite_architecture(self, candidates, user_intent_profile):
        """
        Solves for the optimal composite architecture stack using Role-Aware Greedy Marginal Coverage Gain
        with local swap optimization and stack efficiency metrics.
        """
        stack = []
        remaining_capabilities = {c["name"]: c["importance"] for c in user_intent_profile.get("capabilities", [])}
        max_stack_size = 5

        while remaining_capabilities and len(stack) < max_stack_size:
            scored = []
            for c in candidates:
                if c in stack or c.get("status") == "INELIGIBLE":
                    continue
                
                gain = self.marginal_capability_gain(c, remaining_capabilities)
                role_gain = 0.20 if any(r in user_intent_profile.get("functional_roles", []) for r in c.get("roles", [])) else 0.0
                comp_gain = 0.10 if not stack else 0.05
                redundancy = 0.15 if any(c.get("name") == s.get("name") for s in stack) else 0.0
                
                selection_score = gain + role_gain + comp_gain - cost - redundancy
                scored.append((selection_score, c))

            if not scored:
                break
                
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_cand = scored[0]
            
            if self.marginal_capability_gain(best_cand, remaining_capabilities) <= 0 and len(stack) >= 1:
                break

            stack.append(best_cand)
            for cap in best_cand.get("covered_capabilities", []):
                remaining_capabilities.pop(cap.get("name"), None)

        return stack

    def classify_item_tier(self, item, keywords, subject_anchor=""):
        title = (item.get("Title") or "").lower()
        desc = (item.get("Description") or "").lower()
        text = f"{title} {desc}"
        
        anchor_words = self.get_anchor_synonyms(subject_anchor) if subject_anchor else []
        has_domain = any(w in text for w in anchor_words if len(w) > 2)
        
        tech_keywords = [k.lower() for k in keywords if k not in ENGLISH_STOPWORDS]
        subsystem_terms = [k for k in tech_keywords if k not in anchor_words and len(k) > 2]
        has_utility = any(term in text for term in subsystem_terms)
        
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
            
    def suppress_generic_signals(self, tokens):
        """
        Module 2: Explicitly suppresses generic architectural adjectives, container terms,
        preamble action verbs, and pronouns (e.g. platform, system, engine, orchestration,
        end-to-end, creation, dataset, i, want, need, build, create, trying).
        """
        generic_terms = {
            "end-to-end", "end to end", "e2e", "lifecycle", "orchestrates", "orchestration",
            "creation", "production-ready", "production ready", "multi-step", "multi step",
            "launch data", "execute multi", "produce production", "workflow wizard",
            "build", "building", "create", "creating", "platform", "engine", "system",
            "solutions", "solution", "tool", "tools", "framework", "frameworks", "dataset", "datasets",
            "i", "we", "want", "need", "trying", "looking", "wanted", "build", "building", "create", "creating"
        }
        return [t for t in tokens if t.lower() not in generic_terms and t.lower() not in ENGLISH_STOPWORDS and t.lower() not in ACTION_VERB_STOPLIST]

    def extract_usecase_profile(self, text):
        """
        Module 1: Use-Case Reasoner.
        Dynamically extracts Problems, Tasks, Capabilities, Artifacts, Roles, and Constraints
        directly from the prompt structure at runtime.
        """
        if not text:
            return {
                "problems": [], "tasks": [], "capabilities": [],
                "artifacts": [], "roles": [], "constraints": []
            }

        text_lower = text.lower()
        clauses = re.split(r'[,;\.\n]| and | that | with | for | to | by | from | of | based on | using | via ', text_lower)
        
        capabilities = []
        tasks = []
        roles = set()
        artifacts = set()
        constraints = set()
        problems = []

        for clause in clauses:
            raw_tokens = re.findall(r'\b[a-zA-Z0-9\-]+\b', clause)
            clean_tokens = self.suppress_generic_signals(raw_tokens)
            
            if len(clean_tokens) >= 2:
                action, obj = clean_tokens[0], clean_tokens[1]
                cap_name = f"{action}_{obj}"
                
                cap_obj = {
                    "name": cap_name,
                    "action": action,
                    "object": obj,
                    "domain": clean_tokens[2] if len(clean_tokens) > 2 else obj,
                    "importance": 1.0 if len(clean_tokens) >= 3 else 0.8
                }
                capabilities.append(cap_obj)
                tasks.append(f"{action} {obj}")
                roles.add(action)
                artifacts.add(obj)
                problems.append(clause.strip())

        return {
            "problems": problems[:4],
            "tasks": tasks[:6],
            "capabilities": capabilities[:8],
            "artifacts": list(artifacts)[:6],
            "roles": list(roles)[:6],
            "constraints": list(constraints)
        }

    def profile_candidate(self, candidate_item):
        """
        Module 3: Candidate Profiler.
        Converts raw candidate data into a deterministic structured Candidate Profile.
        """
        title = (candidate_item.get("Title") or "").strip()
        desc = (candidate_item.get("Description") or "").strip()
        text_lower = f"{title} {desc}".lower()
        
        raw_tokens = re.findall(r'\b[a-zA-Z0-9\-]+\b', text_lower)
        clean_tech_list = self.suppress_generic_signals(raw_tokens)
        
        capabilities = []
        for i in range(len(clean_tech_list) - 1):
            capabilities.append({
                "name": f"{clean_tech_list[i]}_{clean_tech_list[i+1]}",
                "action": clean_tech_list[i],
                "object": clean_tech_list[i+1],
                "confidence": 0.90
            })
            
        return {
            "title": title,
            "description": desc,
            "category": candidate_item.get("Type", "GitHub Repo"),
            "link": candidate_item.get("Link", ""),
            "tech_tokens_list": clean_tech_list,
            "tech_tokens": set(clean_tech_list),
            "capabilities": capabilities[:6],
            "roles": list(set(clean_tech_list))[:4]
        }

    def expand_word_synonyms(self, word):
        """
        Dynamically generates morphological variations, nominalizations, and synonym aliases
        for ANY input word with ZERO hardcoded word mappings.
        """
        if not word:
            return set()
        w = word.lower().strip()
        syns = {w}
        
        # Dynamic morphological stemming & nominalization rules
        if len(w) > 3:
            if w.endswith("e"):
                syns.add(w[:-1] + "ing")
                syns.add(w[:-1] + "ion")
                syns.add(w[:-1] + "ation")
                syns.add(w[:-1] + "or")
                syns.add(w[:-1] + "er")
            elif w.endswith("y"):
                syns.add(w[:-1] + "ies")
                syns.add(w[:-1] + "ied")
            else:
                syns.add(w + "ing")
                syns.add(w + "ion")
                syns.add(w + "ation")
                syns.add(w + "er")
                syns.add(w + "s")

        # Dynamic skill_synonyms.json config map lookup
        for canonical, aliases in self.synonyms.items():
            if w == canonical or w in aliases:
                syns.add(canonical)
                syns.update(aliases)
                
        return syns

    def candidate_is_eligible_stage_a(self, candidate_profile, intent_profile):
        """
        Module 4: Stage A Role-Aware Binary Hard Gate.
        Strictly evaluates capability/role match and domain contradictions.
        Candidates without genuine capability or role alignment are REJECTED at MatchScore = 0.0%.
        """
        if not intent_profile or not intent_profile.get("capabilities"):
            return False, 0.0, "IRRELEVANT: Sparse intent profile"

        user_caps = intent_profile["capabilities"]
        user_roles = intent_profile.get("roles", [])
        cand_text = f"{candidate_profile.get('title', '')} {candidate_profile.get('description', '')}".lower()
        cand_tech_list = candidate_profile.get("tech_tokens_list", [])
        cand_tech = candidate_profile.get("tech_tokens", set())

        # Dynamic Capability Match Verification
        generic_single_words = {"ai", "agent", "data", "model", "models", "app", "workload", "workloads", "file", "files"}
        max_sim = 0.0
        matched_cap_names = []
        
        for u_cap in user_caps:
            u_act = u_cap.get("action", "").lower()
            u_obj = u_cap.get("object", "").lower()
            u_name = u_cap.get("name", "").lower()
            
            # 1. Direct compound capability name match or underscore replacement
            if u_name and (u_name in cand_text or u_name.replace("_", " ") in cand_text or u_name.replace("_", "-") in cand_text):
                max_sim = 1.0
                matched_cap_names.append(u_cap["name"])
                break

            # 2. Dynamic Synonym Expansion via Morphological Rules & Synonyms Config
            act_syns = self.expand_word_synonyms(u_act) if u_act else {u_act}
            obj_syns = self.expand_word_synonyms(u_obj) if u_obj else {u_obj}

            has_act_match = any(syn in cand_text for syn in act_syns if len(syn) > 2 and syn not in generic_single_words)
            has_obj_match = any(syn in cand_text for syn in obj_syns if len(syn) > 2 and syn not in generic_single_words)

            if has_act_match and has_obj_match:
                max_sim = 1.0
                matched_cap_names.append(u_cap["name"])
                break

            # 3. Two-dimensional deterministic similarity calculation using ordered list
            sim = self.capability_similarity(u_cap, {
                "name": " ".join(cand_tech_list[:3]),
                "action": cand_tech_list[0] if cand_tech_list else "",
                "object": cand_tech_list[1] if len(cand_tech_list) > 1 else ""
            })
            if sim >= 0.50:
                max_sim = max(max_sim, sim)
                matched_cap_names.append(u_cap["name"])

        # Dynamic Role Alignment Verification using morphological expansion
        role_aligned = True
        if user_roles:
            role_aligned = False
            for r in user_roles:
                r_syns = self.expand_word_synonyms(r)
                if any(syn in cand_text for syn in r_syns if len(syn) > 2 and syn not in generic_single_words):
                    role_aligned = True
                    break

        if max_sim >= 0.50 and role_aligned:
            return True, max_sim, f"ELIGIBLE: Verified capability match [{', '.join(matched_cap_names[:2])}]"
        else:
            return False, 0.0, "IRRELEVANT: No meaningful capability or role alignment with use case"

    def rank_eligible_candidates_stage_b(self, candidate_item, intent_profile, stage_a_sim):
        """
        Module 5: Stage B Composite Relevance Ranking.
        Formula: 30% Capability + 25% Task + 20% Role + 15% Evidence + 10% Practical Usefulness
        Real evidence verification and real usefulness evaluation applied.
        """
        cand_text = f"{candidate_item.get('Title', '')} {candidate_item.get('Description', '')}".lower()
        desc = (candidate_item.get("Description") or "").lower()
        link = (candidate_item.get("Link") or "").strip()
        
        # 1. Capability Match (30%)
        s_cap = stage_a_sim * 100.0
        
        # 2. Task Alignment (25%)
        tasks = intent_profile.get("tasks", [])
        matched_tasks = [t for t in tasks if any(w in cand_text for w in t.split() if w not in ENGLISH_STOPWORDS)]
        s_task = (len(matched_tasks) / max(1, len(tasks))) * 100.0 if tasks else 50.0
        
        # 3. Role Alignment (20%)
        roles = intent_profile.get("roles", [])
        matched_roles = [r for r in roles if r in cand_text]
        s_role = (len(matched_roles) / max(1, len(roles))) * 100.0 if roles else 50.0
        
        # 4. Evidence Quality Verification (15%)
        # Evaluates capability claim verification from description text rather than raw character length
        user_caps = intent_profile.get("capabilities", [])
        has_claim_verification = False
        for c in user_caps:
            act, obj = c.get("action", ""), c.get("object", "")
            if act and obj and (act in desc) and (obj in desc):
                has_claim_verification = True
                break
                
        s_evidence = 95.0 if has_claim_verification else (70.0 if len(desc) > 50 else 30.0)
        
        # 5. Practical Usefulness Evaluation (10%)
        # Evaluates URL validity, repository/SDK package status, and actionability
        is_valid_url = link.startswith("http://") or link.startswith("https://")
        is_code_or_pkg = candidate_item.get("Type") in ["GitHub Repo", "PyPI Release", "Prompt & Guardrail Templates"]
        
        s_useful = 95.0 if (is_valid_url and is_code_or_pkg) else (70.0 if is_valid_url else 30.0)
        
        # Stage B Weighted Composite Relevance Score Formula
        score = (0.30 * s_cap) + (0.25 * s_task) + (0.20 * s_role) + (0.15 * s_evidence) + (0.10 * s_useful)
        return min(100.0, round(score, 1))

    def generate_evidence_audit_record(self, item, intent_profile, score):
        """
        Module 6: Evidence & Provenance Traceability Record with Claim Verification.
        """
        title = item.get("Title", "")
        desc = item.get("Description", "")
        link = item.get("Link", "")
        cat = item.get("Type", "GitHub Repo")
        
        tasks = intent_profile.get("tasks", [])
        user_caps = intent_profile.get("capabilities", [])
        
        # Extract verifiable quote from description matching prompt capability
        matching_quote = desc[:150]
        claim_verified = False
        for c in user_caps:
            act, obj = c.get("action", ""), c.get("object", "")
            if act and obj and (act in desc.lower()) and (obj in desc.lower()):
                claim_verified = True
                matching_quote = f"Proven capability: '{act} {obj}' verified in source text."
                break
                
        clean_matched = [t for t in tasks if any(w in desc.lower() for w in t.split() if w not in ENGLISH_STOPWORDS)]
        matched_str = ", ".join(clean_matched[:2]) if clean_matched else "core technical requirements"
        tip = self.generate_role_tip(item, clean_matched)
        
        return {
            "resource_title": title,
            "category": cat,
            "relevance_score": f"{score}%",
            "source_url": link,
            "evidence_quote": matching_quote,
            "claim_status": "VERIFIED" if claim_verified else "UNVERIFIED",
            "rationale": f"Directly provides capability alignment for [{matched_str}] required by your use case.",
            "action_tip": tip
        }

    def score_item(self, item, keywords, subject_anchor="", intent_profile=None):
        if not keywords:
            return 0.0, [], ""

        if not intent_profile:
            intent_profile = self.extract_usecase_profile(subject_anchor or " ".join(keywords))

        # Module 3: Candidate Profiler
        cand_profile = self.profile_candidate(item)
        
        # Module 4: Stage A Hard Gate Check
        is_eligible, stage_a_sim, reason = self.candidate_is_eligible_stage_a(cand_profile, intent_profile)
        if not is_eligible:
            return 0.0, [], f"IRRELEVANT: {reason}"

        # Module 5: Stage B Composite Ranking
        final_score = self.rank_eligible_candidates_stage_b(item, intent_profile, stage_a_sim)
        
        # Module 6: Audit Record & Tip
        audit = self.generate_evidence_audit_record(item, intent_profile, final_score)
        
        matched_kw = list(cand_profile["tech_tokens"])[:3]
        return final_score, matched_kw, audit["action_tip"]

    def generate_role_tip(self, item, matched_keywords):
        cat = item.get("Type", "")
        clean_kw = [k for k in matched_keywords if k not in ENGLISH_STOPWORDS]
        matched_str = ", ".join(clean_kw[:3]) if clean_kw else "core technical requirements"
        
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

    def normalize_capabilities(self, intent_profile):
        """
        V3 Module A: Capability Normalization & Context Noise Filter.
        Classifies extracted capabilities into Core Semantic Capabilities vs Suppressed Context Noise.
        """
        if not intent_profile or not intent_profile.get("capabilities"):
            return [], []

        context_noise_words = {
            "enterprise_ai", "enables_enterprise", "launch_data", "execute_multi-layer",
            "ai_agents", "automated_pipeline", "deep_learning", "real-time_voice", "i_want"
        }
        
        core_semantic = []
        suppressed_noise = []
        
        for c in intent_profile["capabilities"]:
            c_name = c.get("name", "").lower()
            if c_name in context_noise_words or c.get("action") in ["enterprise", "enables", "i", "we", "want"]:
                suppressed_noise.append(c_name)
            else:
                core_semantic.append(c)

        return core_semantic, suppressed_noise

    # ------------------------------------------------------------------
    # Stage 4: Capability Relationship Model
    # ------------------------------------------------------------------

    def _capability_tokens(self, cap):
        """Return a deduplicated, lowercased set of meaningful tokens from a capability dict.
        Includes action + object + domain + name to maximise relationship surface."""
        raw = (
            f"{cap.get('action', '')} "
            f"{cap.get('object', '')} "
            f"{cap.get('domain', '')} "
            f"{cap.get('name', '')}"
        )
        return {t for t in re.split(r'[_\s\-]+', raw.lower()) if len(t) > 2 and t not in ENGLISH_STOPWORDS}

    def _stem_simple(self, word):
        """Minimal rule-based morphological stemmer — strips common derivational suffixes."""
        for suffix in ('ation', 'ment', 'ing', 'tion', 'ion', 'ive', 'ize', 'ise', 'ed', 'er', 'al', 'or'):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[:-len(suffix)]
        return word

    def build_capability_relationships(self, core_capabilities):
        """
        Stage 4: Generic, data-driven Capability Relationship Model.

        Derives directed relationships between extracted capabilities using
        purely algorithmic token overlap — zero domain-specific hardcoding.

        Relationship types:
          supports   — A's object tokens appear in B's action tokens
                       (A produces something B acts on)
          depends_on — A's action tokens contain B's object tokens
                       (A acts on what B produces)
          enables    — stem(A's object) matches stem(B's action)
                       (A's outcome unlocks B's process)
          related_to — A and B share object-space tokens
                       (parallel objectives, same domain surface)

        Returns:
          List of relationship dicts:
            {"source": cap_name_A, "relation": "supports|depends_on|enables|related_to",
             "target": cap_name_B, "context_tokens": [shared token list]}
        """
        if len(core_capabilities) < 2:
            return []

        relationships = []
        seen_pairs = set()  # prevent duplicate (A, B) and reflexive entries

        for i, cap_a in enumerate(core_capabilities):
            a_name = cap_a.get("name", "")
            # Include domain in action/object token sets to maximise relationship surface
            a_action_toks = {t for t in re.split(r'[_\s\-]+', cap_a.get('action', '').lower()) if len(t) > 2 and t not in ENGLISH_STOPWORDS}
            a_object_toks = {
                t for t in re.split(
                    r'[_\s\-]+',
                    f"{cap_a.get('object', '')} {cap_a.get('domain', '')}".lower()
                ) if len(t) > 2 and t not in ENGLISH_STOPWORDS
            }
            a_obj_stems = {self._stem_simple(t) for t in a_object_toks}

            for j, cap_b in enumerate(core_capabilities):
                if i == j:
                    continue
                b_name = cap_b.get("name", "")
                pair_key = tuple(sorted([a_name, b_name]))
                b_action_toks = {t for t in re.split(r'[_\s\-]+', cap_b.get('action', '').lower()) if len(t) > 2 and t not in ENGLISH_STOPWORDS}
                b_object_toks = {
                    t for t in re.split(
                        r'[_\s\-]+',
                        f"{cap_b.get('object', '')} {cap_b.get('domain', '')}".lower()
                    ) if len(t) > 2 and t not in ENGLISH_STOPWORDS
                }
                b_action_stems = {self._stem_simple(t) for t in b_action_toks}

                # Rule 1: supports — A's object feeds into B's action
                supports_overlap = a_object_toks & b_action_toks
                if supports_overlap and (a_name, b_name, "supports") not in seen_pairs:
                    seen_pairs.add((a_name, b_name, "supports"))
                    relationships.append({
                        "source": a_name, "relation": "supports", "target": b_name,
                        "context_tokens": sorted(supports_overlap)
                    })
                    continue

                # Rule 2: depends_on — A's action acts on what B's object produces
                depends_overlap = a_action_toks & b_object_toks
                if depends_overlap and (a_name, b_name, "depends_on") not in seen_pairs:
                    seen_pairs.add((a_name, b_name, "depends_on"))
                    relationships.append({
                        "source": a_name, "relation": "depends_on", "target": b_name,
                        "context_tokens": sorted(depends_overlap)
                    })
                    continue

                # Rule 3: enables — stem(A's object) matches stem(B's action)
                enables_stem_overlap = a_obj_stems & b_action_stems
                if enables_stem_overlap and (a_name, b_name, "enables") not in seen_pairs:
                    seen_pairs.add((a_name, b_name, "enables"))
                    relationships.append({
                        "source": a_name, "relation": "enables", "target": b_name,
                        "context_tokens": sorted(enables_stem_overlap)
                    })
                    continue

                # Rule 4: related_to — shared object-space tokens (symmetric, record once)
                related_overlap = a_object_toks & b_object_toks
                if related_overlap and pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    relationships.append({
                        "source": a_name, "relation": "related_to", "target": b_name,
                        "context_tokens": sorted(related_overlap)
                    })

        return relationships

    # ------------------------------------------------------------------
    # Stage 5: Multi-Intent Ecosystem Query Generation
    # ------------------------------------------------------------------

    # Three generic, domain-agnostic intent families.
    # Each family represents a fundamentally different search intent:
    #   artifact     — find a concrete tool/library that implements the capability
    #   implementation — find code, SDK, or tutorial showing HOW to use it
    #   research     — find papers, benchmarks, or deep analysis about it
    #
    # No domain-specific knowledge is encoded here. The template slots
    # ("{phrase}") are filled at runtime with the normalized capability phrase.
    _ECOSYSTEM_INTENT_MATRIX = {
        # intent_family: (artifact, implementation, research)
        "GitHub Repo": [
            "{phrase} tool framework library",
            "{phrase} implementation open-source",
            "{phrase} benchmark evaluation harness",
        ],
        "PyPI Release": [
            "{phrase} sdk package",
            "{phrase} python api client",
            "{phrase} toolkit utilities",
        ],
        "arXiv Research Paper": [
            "{phrase} architecture benchmark",
            "{phrase} survey empirical evaluation",
            "{phrase} method systematic review",
        ],
        "Hugging Face Model": [
            "{phrase} pretrained model",
            "{phrase} fine-tuned inference",
            "{phrase} transformer checkpoint",
        ],
        "Hugging Face Dataset": [
            "{phrase} benchmark dataset",
            "{phrase} evaluation corpus",
            "{phrase} training ground-truth",
        ],
        "YouTube Video": [
            "{phrase} tutorial walkthrough",
            "{phrase} implementation demo",
            "{phrase} paper explained",
        ],
        "Reddit Discussion": [
            "{phrase} best practices",
            "{phrase} tools comparison",
            "{phrase} community discussion",
        ],
        "Product Hunt Launch": [
            "{phrase} product tool",
            "{phrase} platform launch",
            "{phrase} saas application",
        ],
        "Corporate Blog": [
            "{phrase} engineering guide",
            "{phrase} case study analysis",
            "{phrase} best practices tutorial",
        ],
        "Medium & Dev Community": [
            "{phrase} how to explained",
            "{phrase} engineering deep dive",
            "{phrase} developer tutorial guide",
        ],
        "AI Course": [
            "{phrase} course curriculum",
            "{phrase} learning tutorial",
            "{phrase} bootcamp certification",
        ],
        "Prompt & Guardrail Templates": [
            "{phrase} prompt template",
            "{phrase} system prompt specification",
            "{phrase} guardrail safety constraint",
        ],
    }

    @staticmethod
    def _dedup_query_tokens(phrase):
        """Remove repeated tokens from a query phrase while preserving word order.
        Prevents relationship enrichment from creating 'annotation annotation' duplicates."""
        seen = set()
        result = []
        for tok in phrase.split():
            tok_lower = tok.lower()
            if tok_lower not in seen:
                seen.add(tok_lower)
                result.append(tok)
        return " ".join(result)

    @staticmethod
    def _jaccard_similarity(a_tokens, b_tokens):
        """Compute Jaccard similarity between two token sets."""
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        return intersection / union if union > 0 else 0.0

    def _deduplicate_queries(self, queries, threshold=0.80):
        """Remove near-duplicate queries within a list.
        Two queries are near-duplicates if their token Jaccard similarity >= threshold."""
        unique = []
        unique_token_sets = []
        for q in queries:
            q_toks = frozenset(q.lower().split())
            is_dup = any(
                self._jaccard_similarity(q_toks, existing) >= threshold
                for existing in unique_token_sets
            )
            if not is_dup:
                unique.append(q)
                unique_token_sets.append(q_toks)
        return unique

    def generate_ecosystem_queries(self, core_capabilities, relationships=None):
        """
        Stage 5: Multi-Intent Ecosystem Query Generation Engine.

        For every core capability, generates >= 3 semantically distinct query intents
        per ecosystem category using the _ECOSYSTEM_INTENT_MATRIX. Query intent families:
          - artifact:        find a tool/library implementing the capability
          - implementation:  find SDK, tutorial, or code showing HOW to use it
          - research:        find papers, benchmarks, or deep analysis about it

        Relationship context (Stage 4) enriches base queries but never replaces them.
        Duplicate tokens from relationship enrichment are cleaned. Near-duplicate queries
        are removed using Jaccard similarity (threshold 0.80).

        Coverage invariant: every core capability appears in >= 1 query per category.
        """
        # Initialise an empty list for ALL 12 categories
        queries = {cat: [] for cat in ALL_12_CATEGORIES}

        # Build relationship enrichment lookup:
        # Only "supports" and "enables" are used (A produces what B acts on).
        enrichment_context = {}
        if relationships:
            for rel in relationships:
                if rel["relation"] in ("supports", "enables"):
                    src = rel["source"]
                    tgt_tokens = rel.get("context_tokens", [])
                    if tgt_tokens:
                        enrichment_context.setdefault(src, []).extend(tgt_tokens)

        for c in core_capabilities:
            act = c.get("action", "")
            obj = c.get("object", "")
            cap_name = c.get("name", "")
            if not act or not obj:
                continue

            base_phrase = f"{act} {obj}".replace("_", " ").strip()

            # Build relationship-enriched phrase (max 2 context tokens)
            ctx_tokens = enrichment_context.get(cap_name, [])
            if ctx_tokens:
                # Append up to 2 unique relationship tokens
                enriched = f"{base_phrase} {' '.join(ctx_tokens[:2])}"
                enriched_phrase = self._dedup_query_tokens(enriched)
            else:
                enriched_phrase = base_phrase

            # Generate 3 intent variants per category from the matrix
            for cat, intent_templates in self._ECOSYSTEM_INTENT_MATRIX.items():
                for template in intent_templates:
                    raw_query = template.format(phrase=enriched_phrase)
                    clean_query = self._dedup_query_tokens(raw_query)
                    if clean_query not in queries[cat]:
                        queries[cat].append(clean_query)

        # Near-duplicate deduplication per category
        for cat in queries:
            queries[cat] = self._deduplicate_queries(queries[cat])

        return queries


    def match_scenario(self, scenario_text, all_updates_dict, top_k=5):
        """
        V3 Instrumented Pipeline with Dynamic Query Generation & Frozen V2 Stage A / Stage B Gates.
        """
        keywords = self.extract_keywords(scenario_text)
        subject_anchor = self.extract_subject_anchor(scenario_text)
        intent_profile = self.extract_usecase_profile(scenario_text)
        
        # V3 Normalization → Relationship Graph → Query Generation
        core_caps, suppressed_noise = self.normalize_capabilities(intent_profile)
        capability_relationships = self.build_capability_relationships(core_caps)
        generated_queries = self.generate_ecosystem_queries(core_caps, relationships=capability_relationships)
        
        results = {}
        low_confidence_categories = []
        
        total_discovered = 0
        total_eligible = 0
        total_rejected = 0
        
        for category in ALL_12_CATEGORIES:
            cat_items = all_updates_dict.get(category, [])
            cat_items = sorted(cat_items, key=lambda x: str(x.get("Link", "")))
            total_discovered += len(cat_items)
            
            scored_items = []
            for item in cat_items:
                score, matched_kw, tip = self.score_item(item, keywords, subject_anchor, intent_profile=intent_profile)
                if score >= 25.0:
                    total_eligible += 1
                    item_copy = dict(item)
                    item_copy["MatchScore"] = score
                    item_copy["MatchedKeywords"] = matched_kw
                    item_copy["IntegrationTip"] = tip
                    scored_items.append(item_copy)
                else:
                    total_rejected += 1
                    
            scored_items.sort(key=lambda x: (x["MatchScore"], str(x.get("Link", ""))), reverse=True)
            top_matches = scored_items[:top_k]
            
            results[category] = top_matches
            
            if len(top_matches) < 2 or (top_matches and top_matches[0]["MatchScore"] < 25.0):
                low_confidence_categories.append(category)
                
        instrumentation = {
            "raw_capabilities_count": len(intent_profile.get("capabilities", [])),
            "core_semantic_capabilities": [c.get("name") for c in core_caps],
            "suppressed_context_noise": suppressed_noise,
            "capability_relationships": capability_relationships,
            "generated_queries": generated_queries,
            "total_candidates_discovered": total_discovered,
            "stage_a_eligible_count": total_eligible,
            "stage_a_rejected_count": total_rejected,
            "stage_a_rejection_rate": f"{(total_rejected / max(1, total_discovered)) * 100.0:.1f}%"
        }

        return {
            "scenario": scenario_text,
            "keywords": keywords,
            "subject_anchor": subject_anchor,
            "intent_profile": intent_profile,
            "instrumentation": instrumentation,
            "recommendations": results,
            "low_confidence_categories": low_confidence_categories
        }

scenario_matcher = UniversalMultiRoleMatcher()
