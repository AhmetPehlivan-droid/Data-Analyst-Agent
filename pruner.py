from typing import Dict, List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class SchemaPruner:
    def __init__(self, table_schemas: Dict[str, str]):
        self.table_schemas = table_schemas
        self.table_names = list(table_schemas.keys())
        
        # Alan terimlerini genişletmek için semantik ipuçları
        domain_hints = {
            "payment": "money spent amount revenue paid customer cost financial total",
            "rental": "rented transactions inventory hire duration return date",
            "film": "movies title length duration description rating release year",
            "actor": "cast stars appearance first_name last_name",
            "customer": "client user buyers email first_name last_name active",
            "inventory": "stock available copies items store",
            "category": "genre type category action comedy animation",
        }
        
        # Her tablo için metin gövdesi oluşturuyoruz
        self.corpus = []
        for name, schema in table_schemas.items():
            hint = domain_hints.get(name.lower(), "")
            self.corpus.append(f"Table: {name} {hint} Columns: {schema}")
            
        self.vectorizer = TfidfVectorizer(stop_words='english', lowercase=True, ngram_range=(1, 2))
        self.schema_matrix = self.vectorizer.fit_transform(self.corpus)

    def prune_schema(self, user_query: str, top_k: int = 7) -> str:
        """
        Kullanıcı sorusuyla en çok eşleşen top_k tablonun şemasını birleştirip döner.
        """
        if not self.table_schemas:
            return ""

        if len(self.table_names) <= top_k:
            return "\n\n".join(self.table_schemas.values())

        query_vec = self.vectorizer.transform([user_query])
        scores = cosine_similarity(query_vec, self.schema_matrix).flatten()
        
        # En yüksek benzerliğe sahip top_k tablo indeksini bul
        top_indices = scores.argsort()[-top_k:][::-1]
        selected_tables = [self.table_names[i] for i in top_indices]
        
        print(f"\n[RAG Schema Pruner] Kullanıcı Sorusu: '{user_query}'")
        print(f"[RAG Schema Pruner] Filtrelenen Tablolar ({len(selected_tables)}/{len(self.table_names)}): {selected_tables}\n")

        return "\n\n".join([self.table_schemas[name] for name in selected_tables])