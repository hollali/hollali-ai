use chrono::{Datelike, Local};
use pyo3::prelude::*;
use rand::Rng;

#[pyfunction]
fn today_date() -> String {
    let now = Local::now();
    let day = now.day();
    let suffix = if (11..=13).contains(&day) {
        "th"
    } else {
        match day % 10 {
            1 => "st",
            2 => "nd",
            3 => "rd",
            _ => "th",
        }
    };
    format!(
        "Today is {}, {} the {}{}.",
        now.format("%A"),
        now.format("%B"),
        day,
        suffix
    )
}

#[pyfunction]
fn say_hello(text: &str) -> String {
    const GREETINGS: &[&str] = &["hi", "hey", "hola", "greetings", "wassup", "hello"];
    const RESPONSES: &[&str] = &["howdy", "whats good", "hello", "hey there"];
    for word in text.split_whitespace() {
        if GREETINGS.contains(&word.to_lowercase().as_str()) {
            let idx = rand::thread_rng().gen_range(0..RESPONSES.len());
            return format!("{}.", RESPONSES[idx]);
        }
    }
    String::new()
}

#[pyfunction]
fn wiki_person(text: &str) -> Option<String> {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.len() < 4 {
        return None;
    }
    for i in 0..=words.len() - 4 {
        if words[i].eq_ignore_ascii_case("who") && words[i + 1].eq_ignore_ascii_case("is") {
            return Some(format!("{} {}", words[i + 2], words[i + 3]));
        }
    }
    None
}

#[pyfunction]
fn truncate_title(content: &str, max_len: usize) -> String {
    let trimmed = content.trim();
    if trimmed.chars().count() <= max_len {
        trimmed.to_string()
    } else {
        trimmed.chars().take(max_len).collect()
    }
}

#[pyfunction]
fn list_conversations(
    db_path: &str,
    search: &str,
    limit: i64,
) -> PyResult<Vec<(String, String, String)>> {
    let conn = rusqlite::Connection::open(db_path).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    let _ = conn.busy_timeout(std::time::Duration::from_secs(5));
    let pattern = format!("%{}%", search.trim());
    let sql = r#"
        WITH first_user AS (
            SELECT session_id, content,
                   ROW_NUMBER() OVER (
                       PARTITION BY session_id
                       ORDER BY created_at ASC, id ASC
                   ) AS rn
            FROM conversations
            WHERE role = 'user'
        )
        SELECT all_sessions.session_id,
               COALESCE(meta.title, first_user.content, 'Conversation') AS title,
               COALESCE(all_sessions.last, '') AS last
        FROM (
            SELECT session_id, MAX(created_at) AS last
            FROM conversations
            GROUP BY session_id
            UNION
            SELECT session_id, '' AS last
            FROM conversation_metadata
        ) AS all_sessions
        LEFT JOIN conversation_metadata AS meta
               ON meta.session_id = all_sessions.session_id
        LEFT JOIN first_user
               ON first_user.session_id = all_sessions.session_id
              AND first_user.rn = 1
        WHERE (?1 = '%' OR COALESCE(meta.title, first_user.content, '') LIKE ?2)
        ORDER BY all_sessions.last DESC, all_sessions.session_id DESC
        LIMIT ?3
    "#;
    let result = {
        let mut stmt = conn.prepare(sql).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        let rows = stmt.query_map(rusqlite::params![pattern, pattern, limit], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        }).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        let mut result = Vec::new();
        for row in rows {
            result.push(row.map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?);
        }
        result
    };
    let _ = conn.close();
    Ok(result)
}

#[pyfunction]
fn search_contains(haystack: &str, needle: &str) -> bool {
    haystack.to_lowercase().contains(&needle.to_lowercase())
}

#[pymodule]
fn hollali_fast(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(today_date, m)?)?;
    m.add_function(wrap_pyfunction!(say_hello, m)?)?;
    m.add_function(wrap_pyfunction!(wiki_person, m)?)?;
    m.add_function(wrap_pyfunction!(truncate_title, m)?)?;
    m.add_function(wrap_pyfunction!(list_conversations, m)?)?;
    m.add_function(wrap_pyfunction!(search_contains, m)?)?;
    Ok(())
}
