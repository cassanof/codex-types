use std::sync::Arc;

use opentau::{
    completion::{
        local::LocalModelClientBuilder, ArcCompletionEngine, ArcCompletionModel,
        CompletionClientBuilder,
    },
    get_path_from_rootdir,
    langserver::{ts::TsServer, AnnotateType, ArcLangServer, LangServer},
    main_strategies::{MainCtx, MainStrategy, SimpleStrategy, TreeStrategy},
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct EvalSpec {
    pub model: String,
    pub strategy: String,
    pub local_model_socket: Option<String>,
    pub remote_model_key: Option<String>,
    pub language: String,
    pub results_path: String,
    pub dataset_path: String,
    pub num_comps: usize,
    pub retries: usize,
    pub fallback: bool,
    pub stop_at: usize,
    pub enable_defgen: bool,
    pub enable_usages: bool,
    pub depth_limit: Option<usize>,
    pub max_type_quality: u16,
    pub temperature: f64,
    pub types: Vec<AnnotateType>,
}

impl EvalSpec {
    async fn get_langserver(&self) -> ArcLangServer {
        match self.language.as_str() {
            "ts" => {
                let path = get_path_from_rootdir("ts-compiler".to_string());
                Arc::new(
                    TsServer::make(&path)
                        .await
                        .expect("failed to make ts server"),
                )
            }
            _ => {
                eprintln!("Unknown language {}", self.language);
                std::process::exit(1);
            }
        }
    }

    pub async fn get_completion_engine(&self) -> ArcCompletionEngine {
        let langserver = self.get_langserver().await;
        let model: ArcCompletionModel = match self.model.as_str() {
            "santacoder" | "incoder" => {
                let mut builder = LocalModelClientBuilder::new(self.model.clone());
                if let Some(endpoint) = &self.local_model_socket {
                    builder = builder.socket_path(endpoint.clone());
                }

                Arc::new(
                    builder
                        .build()
                        .await
                        .unwrap_or_else(|_| panic!("failed to make {} client", self.model)),
                )
            }
            _ => {
                eprintln!("Unknown model {}", self.model);
                std::process::exit(1);
            }
        };
        let engine = CompletionClientBuilder::new(langserver, model)
            .temperature(self.temperature)
            .max_type_score(self.max_type_quality);
        Arc::new(engine.build())
    }

    pub fn get_strategy(&self) -> Box<dyn MainStrategy> {
        match self.strategy.as_str() {
            "tree" => Box::new(TreeStrategy {}),
            "simple" => Box::new(SimpleStrategy {}),
            _ => {
                eprintln!("Unknown strategy {}", self.strategy);
                std::process::exit(1);
            }
        }
    }

    pub fn make_main_ctx(&self, input_file: String, engine: ArcCompletionEngine) -> MainCtx {
        MainCtx {
            engine,
            file_contents: input_file,
            num_comps: self.num_comps,
            retries: self.retries,
            fallback: self.fallback,
            stop_at: self.stop_at,
            // we do this separately.
            enable_type_check: false,
            enable_defgen: self.enable_defgen,
            enable_usages: self.enable_usages,
            depth_limit: self.depth_limit,
            types: self.types.clone(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DatasetElement {
    pub hexsha: String,
    pub size: usize,
    pub ext: String,
    pub lang: String,
    pub avg_line_length: f64,
    pub max_line_length: usize,
    pub loc: usize,
    pub functions: usize,
    pub function_parameters: usize,
    pub variable_declarations: usize,
    pub property_declarations: usize,
    pub trivial_types: usize,
    pub predefined_types: usize,
    pub type_definitions: usize,
    pub dynamism_heuristic: usize,
    pub estimated_tokens: usize,
    pub content: String,
    pub content_without_annotations: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ResultElement {
    pub dataset_elem: DatasetElement,
    /// This is just for debugging purposes. If the system for some reason
    /// fails, we can see what the error was.
    pub failed_message: Option<String>,
    pub completions: Vec<ResultCompletion>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ResultCompletion {
    pub completion: String,
    pub does_typecheck: bool,
    pub heuristic: u16,
}

pub async fn read_dataset(path: &str) -> Vec<DatasetElement> {
    let dataset_path = if path.starts_with('/') {
        path.to_string()
    } else {
        let cargo_path = std::env::var("CARGO_MANIFEST_DIR").unwrap();
        format!("{cargo_path}/{path}")
    };

    let dataset_file = tokio::fs::read_to_string(dataset_path)
        .await
        .unwrap_or_else(|_| {
            eprintln!("Failed to read input file");
            std::process::exit(1);
        });
    let mut dataset = Vec::new();
    for line in dataset_file.lines() {
        let element: DatasetElement = serde_json::from_str(line).unwrap_or_else(|_| {
            eprintln!("Failed to parse input file");
            std::process::exit(1);
        });
        dataset.push(element);
    }
    dataset
}

pub async fn write_results(results: Vec<ResultElement>, path: &str) {
    let results_path = if path.starts_with('/') {
        path.to_string()
    } else {
        let cargo_path = std::env::var("CARGO_MANIFEST_DIR").unwrap();
        format!("{cargo_path}/{path}")
    };

    let mut lines = String::new();
    for result in results {
        let line = serde_json::to_string(&result).unwrap_or_else(|_| {
            eprintln!("Failed to serialize result");
            std::process::exit(1);
        });
        lines.push_str(&line);
        lines.push('\n');
    }
    tokio::fs::write(results_path, lines).await.unwrap_or_else(|_| {
        eprintln!("Failed to write results");
        std::process::exit(1);
    });
}
