-- ============================================================
-- OpenStudy FastAPI + Vue3-TS  完整部署 SQL
--   PostgreSQL 16 + pgvector + pg_trgm
-- ------------------------------------------------------------
-- 内容：① 建表结构  ② 部门/角色/菜单/参数种子  ③ 演示数据
-- ⚠️ 已清洗：真实 API Key / 密码 / 隐私业务数据均已移除或替换为占位。
--    演示账号密码统一为 admin123，首次登录后请立即修改。
-- 用法：
--   createdb openstudy_v2_pgsql
--   psql -U root -d openstudy_v2_pgsql -f openstudy_v2_pgsql_deploy.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ============================================================
-- ① 建表结构（schema）
-- ============================================================
--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_agent_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agent_config (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    name character varying(64) NOT NULL,
    description character varying(255),
    greeting character varying(500),
    persona_prompt text,
    tools json NOT NULL,
    model character varying(128),
    is_enabled smallint NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_time timestamp without time zone,
    update_time timestamp without time zone
);


--
-- Name: ai_agent_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_agent_config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_agent_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_agent_config_id_seq OWNED BY public.ai_agent_config.id;


--
-- Name: ai_agent_memory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agent_memory (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    memory_type character varying(20) NOT NULL,
    content text NOT NULL,
    metadata json,
    importance integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    del_flag character varying(1) DEFAULT '0'::character varying NOT NULL
);


--
-- Name: ai_agent_memory_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_agent_memory_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_agent_memory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_agent_memory_id_seq OWNED BY public.ai_agent_memory.id;


--
-- Name: ai_agent_op_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agent_op_log (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    session_id character varying(64) NOT NULL,
    turn_id character varying(64) NOT NULL,
    op_index integer NOT NULL,
    tool character varying(64) NOT NULL,
    action character varying(32) NOT NULL,
    op character varying(32) NOT NULL,
    target_table character varying(64) NOT NULL,
    target_ids json,
    before json,
    undoable boolean NOT NULL,
    reason character varying(40) NOT NULL,
    undone_at timestamp without time zone,
    create_time timestamp without time zone
);


--
-- Name: ai_agent_op_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_agent_op_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_agent_op_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_agent_op_log_id_seq OWNED BY public.ai_agent_op_log.id;


--
-- Name: ai_agent_role_pref; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agent_role_pref (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    role_key character varying(32) NOT NULL,
    disabled smallint DEFAULT 0 NOT NULL,
    create_time timestamp without time zone,
    update_time timestamp without time zone
);


--
-- Name: ai_agent_role_pref_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_agent_role_pref_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_agent_role_pref_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_agent_role_pref_id_seq OWNED BY public.ai_agent_role_pref.id;


--
-- Name: ai_agent_timeline; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agent_timeline (
    session_id character varying(64) NOT NULL,
    user_id bigint NOT NULL,
    payload text,
    update_time timestamp without time zone
);


--
-- Name: ai_agent_tool_pref; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agent_tool_pref (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    tool_name character varying(64) NOT NULL,
    disabled smallint DEFAULT 0 NOT NULL,
    create_time timestamp without time zone,
    update_time timestamp without time zone
);


--
-- Name: ai_agent_tool_pref_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_agent_tool_pref_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_agent_tool_pref_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_agent_tool_pref_id_seq OWNED BY public.ai_agent_tool_pref.id;


--
-- Name: ai_chat_message; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_chat_message (
    id bigint NOT NULL,
    session_id character varying(64) NOT NULL,
    user_id bigint NOT NULL,
    role character varying(20) NOT NULL,
    content text,
    attachments text,
    create_time timestamp without time zone,
    turn_id character varying(64) DEFAULT ''::character varying NOT NULL,
    del_flag character varying(1) DEFAULT '0'::character varying NOT NULL
);


--
-- Name: ai_chat_message_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_chat_message_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_chat_message_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_chat_message_id_seq OWNED BY public.ai_chat_message.id;


--
-- Name: ai_chat_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_chat_session (
    session_id character varying(64) NOT NULL,
    user_id bigint NOT NULL,
    title character varying(100),
    message_count integer NOT NULL,
    create_time timestamp without time zone,
    update_time timestamp without time zone
);


--
-- Name: bank_share; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bank_share (
    id bigint NOT NULL,
    bank_id bigint NOT NULL,
    owner_id bigint NOT NULL,
    share_token character varying(64) NOT NULL,
    share_code character varying(12) NOT NULL,
    permission character varying(16) NOT NULL,
    message character varying(200),
    expire_time timestamp without time zone,
    receive_count integer NOT NULL,
    status character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: bank_share_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bank_share_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bank_share_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bank_share_id_seq OWNED BY public.bank_share.id;


--
-- Name: bank_share_receive; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bank_share_receive (
    id bigint NOT NULL,
    share_id bigint NOT NULL,
    bank_id bigint NOT NULL,
    owner_id bigint NOT NULL,
    receiver_id bigint NOT NULL,
    source character varying(16) NOT NULL,
    status character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: bank_share_receive_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bank_share_receive_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bank_share_receive_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bank_share_receive_id_seq OWNED BY public.bank_share_receive.id;


--
-- Name: carousel; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.carousel (
    id bigint NOT NULL,
    title character varying(255),
    image_url character varying(500) NOT NULL,
    link_url character varying(500),
    sort_order integer NOT NULL,
    status character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: carousel_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.carousel_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: carousel_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.carousel_id_seq OWNED BY public.carousel.id;


--
-- Name: chat_message; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_message (
    id bigint NOT NULL,
    sender_id bigint NOT NULL,
    sender_name character varying(100),
    sender_nickname character varying(100),
    sender_avatar character varying(255),
    receiver_id bigint NOT NULL,
    receiver_name character varying(100),
    receiver_nickname character varying(100),
    receiver_avatar character varying(255),
    content text NOT NULL,
    is_read integer,
    is_deleted integer,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    hidden_by character varying(500)
);


--
-- Name: chat_message_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chat_message_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chat_message_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chat_message_id_seq OWNED BY public.chat_message.id;


--
-- Name: courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.courses (
    course_id bigint NOT NULL,
    course_name character varying(255) NOT NULL,
    course_description text,
    cover_image character varying(500),
    user_id bigint,
    category character varying(100),
    status character varying(1) NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: courses_course_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.courses_course_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: courses_course_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.courses_course_id_seq OWNED BY public.courses.course_id;


--
-- Name: leave_message; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leave_message (
    id bigint NOT NULL,
    user_id bigint,
    content text NOT NULL,
    reply_content text,
    status character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: leave_message_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.leave_message_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: leave_message_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.leave_message_id_seq OWNED BY public.leave_message.id;


--
-- Name: note; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note (
    note_id bigint NOT NULL,
    user_id bigint NOT NULL,
    category_id bigint NOT NULL,
    title character varying(255) NOT NULL,
    filename character varying(255) NOT NULL,
    content text,
    markdown_content text,
    tags character varying(500),
    public_section_id bigint,
    cover_image character varying(500),
    is_public integer NOT NULL,
    view_count integer NOT NULL,
    like_count integer NOT NULL,
    comment_count integer NOT NULL,
    status character varying(20) NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: note_category; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_category (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    name character varying(100) NOT NULL,
    order_num integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: note_category_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_category_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_category_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_category_id_seq OWNED BY public.note_category.id;


--
-- Name: note_comment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_comment (
    id bigint NOT NULL,
    note_id bigint NOT NULL,
    user_id bigint NOT NULL,
    content text NOT NULL,
    parent_id bigint,
    reply_to_user_id bigint,
    status integer,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: note_comment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_comment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_comment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_comment_id_seq OWNED BY public.note_comment.id;


--
-- Name: note_note_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_note_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_note_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_note_id_seq OWNED BY public.note.note_id;


--
-- Name: note_public_section; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_public_section (
    id bigint NOT NULL,
    name character varying(50) NOT NULL,
    sort_order integer,
    create_time timestamp without time zone DEFAULT now()
);


--
-- Name: note_public_section_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_public_section_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_public_section_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_public_section_id_seq OWNED BY public.note_public_section.id;


--
-- Name: note_question; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_question (
    id bigint NOT NULL,
    note_id bigint NOT NULL,
    question_id bigint NOT NULL,
    user_id bigint NOT NULL,
    relation_type character varying(32),
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: note_question_bank; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.note_question_bank (
    id bigint NOT NULL,
    note_id bigint NOT NULL,
    question_bank_id bigint NOT NULL,
    user_id bigint NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: note_question_bank_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_question_bank_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_question_bank_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_question_bank_id_seq OWNED BY public.note_question_bank.id;


--
-- Name: note_question_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.note_question_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: note_question_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.note_question_id_seq OWNED BY public.note_question.id;


--
-- Name: question_bank; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_bank (
    id bigint NOT NULL,
    bank_name character varying(100) NOT NULL,
    subject character varying(50),
    description character varying(500),
    cover_image character varying(255),
    total_questions integer NOT NULL,
    status character varying(1) NOT NULL,
    user_id bigint NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    is_public integer NOT NULL,
    allow_fork integer DEFAULT 1 NOT NULL
);


--
-- Name: question_bank_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.question_bank_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: question_bank_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.question_bank_id_seq OWNED BY public.question_bank.id;


--
-- Name: question_main; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_main (
    id bigint NOT NULL,
    bank_id bigint NOT NULL,
    question_type integer NOT NULL,
    difficulty integer NOT NULL,
    question_text text,
    content text,
    options json,
    answer text,
    analysis text,
    has_sub_questions integer NOT NULL,
    sort_order integer NOT NULL,
    score numeric(5,2) NOT NULL,
    status character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: question_main_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.question_main_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: question_main_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.question_main_id_seq OWNED BY public.question_main.id;


--
-- Name: question_sub; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_sub (
    id bigint NOT NULL,
    main_id bigint NOT NULL,
    question_text text NOT NULL,
    question_type integer NOT NULL,
    options json,
    answer character varying(500) NOT NULL,
    analysis text,
    sort_order integer NOT NULL,
    score numeric(5,2) NOT NULL
);


--
-- Name: question_sub_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.question_sub_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: question_sub_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.question_sub_id_seq OWNED BY public.question_sub.id;


--
-- Name: rag_document; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_document (
    id bigint NOT NULL,
    kb_id bigint NOT NULL,
    user_id bigint NOT NULL,
    file_name character varying(255) NOT NULL,
    file_type character varying(50),
    file_size bigint,
    file_path character varying(500),
    raw_content text,
    chunk_count integer NOT NULL,
    status integer NOT NULL,
    error_msg character varying(500),
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: rag_document_chunk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_document_chunk (
    id bigint NOT NULL,
    kb_id bigint NOT NULL,
    doc_id bigint NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    content_length integer,
    token_count integer,
    content_tokens text,
    embedding public.vector(1024),
    search_vec tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, COALESCE(content_tokens, ''::text))) STORED,
    meta_data json,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: rag_document_chunk_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_document_chunk_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_document_chunk_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_document_chunk_id_seq OWNED BY public.rag_document_chunk.id;


--
-- Name: rag_document_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_document_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_document_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_document_id_seq OWNED BY public.rag_document.id;


--
-- Name: rag_knowledge_base; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_knowledge_base (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    embedding_model character varying(100) NOT NULL,
    embedding_dim integer NOT NULL,
    chunk_size integer NOT NULL,
    chunk_overlap integer NOT NULL,
    doc_count integer NOT NULL,
    chunk_count integer NOT NULL,
    status character varying(1) NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone,
    disabled smallint DEFAULT 0 NOT NULL
);


--
-- Name: rag_knowledge_base_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_knowledge_base_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_knowledge_base_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_knowledge_base_id_seq OWNED BY public.rag_knowledge_base.id;


--
-- Name: rag_qa_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rag_qa_record (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    kb_id bigint,
    question text NOT NULL,
    answer text,
    retrieved_chunks json,
    duration_ms integer,
    feedback integer,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: rag_qa_record_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rag_qa_record_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rag_qa_record_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rag_qa_record_id_seq OWNED BY public.rag_qa_record.id;


--
-- Name: sys_ai_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_ai_config (
    config_id bigint NOT NULL,
    user_id bigint,
    provider character varying(50) NOT NULL,
    provider_name character varying(100),
    model character varying(100) NOT NULL,
    api_key character varying(500),
    base_url character varying(500),
    web_phone character varying(50),
    web_password character varying(200),
    web_area_code character varying(10),
    is_default smallint NOT NULL,
    is_enabled smallint NOT NULL,
    status character varying(1),
    remark character varying(500),
    thinking_mode character varying(20),
    reasoning_effort character varying(20),
    context_length character varying(20),
    create_time timestamp without time zone,
    update_time timestamp without time zone,
    create_by character varying(64),
    update_by character varying(64),
    model_kind character varying(20)
);


--
-- Name: sys_ai_config_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_ai_config_config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_ai_config_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_ai_config_config_id_seq OWNED BY public.sys_ai_config.config_id;


--
-- Name: sys_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_config (
    config_id bigint NOT NULL,
    config_name character varying(100),
    config_key character varying(100),
    config_value character varying(500),
    config_type character varying(1) NOT NULL,
    create_by character varying(64),
    create_time timestamp without time zone,
    update_by character varying(64),
    update_time timestamp without time zone,
    remark character varying(500)
);


--
-- Name: sys_config_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_config_config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_config_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_config_config_id_seq OWNED BY public.sys_config.config_id;


--
-- Name: sys_dept; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_dept (
    dept_id bigint NOT NULL,
    parent_id bigint NOT NULL,
    ancestors character varying(500),
    dept_name character varying(30) NOT NULL,
    order_num integer NOT NULL,
    leader character varying(20),
    phone character varying(11),
    email character varying(50),
    status character varying(1) NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_time timestamp without time zone,
    update_time timestamp without time zone
);


--
-- Name: sys_dept_dept_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_dept_dept_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_dept_dept_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_dept_dept_id_seq OWNED BY public.sys_dept.dept_id;


--
-- Name: sys_menu; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_menu (
    menu_id bigint NOT NULL,
    menu_name character varying(50) NOT NULL,
    parent_id bigint NOT NULL,
    order_num integer NOT NULL,
    path character varying(200),
    component character varying(255),
    query character varying(255),
    is_frame integer NOT NULL,
    is_cache integer NOT NULL,
    menu_type character varying(1) NOT NULL,
    visible character varying(1) NOT NULL,
    status character varying(1) NOT NULL,
    perms character varying(100),
    icon character varying(100) NOT NULL,
    create_by character varying(64),
    create_time timestamp without time zone,
    update_by character varying(64),
    update_time timestamp without time zone,
    remark character varying(500)
);


--
-- Name: sys_menu_menu_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_menu_menu_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_menu_menu_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_menu_menu_id_seq OWNED BY public.sys_menu.menu_id;


--
-- Name: sys_notice; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_notice (
    notice_id bigint NOT NULL,
    notice_title character varying(50) NOT NULL,
    notice_type character varying(1) NOT NULL,
    notice_content text,
    status character varying(1) NOT NULL,
    create_by character varying(64),
    create_time timestamp without time zone,
    update_by character varying(64),
    update_time timestamp without time zone,
    remark character varying(255)
);


--
-- Name: sys_notice_delete; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_notice_delete (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    notice_id bigint NOT NULL,
    delete_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: sys_notice_delete_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_notice_delete_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_notice_delete_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_notice_delete_id_seq OWNED BY public.sys_notice_delete.id;


--
-- Name: sys_notice_notice_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_notice_notice_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_notice_notice_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_notice_notice_id_seq OWNED BY public.sys_notice.notice_id;


--
-- Name: sys_notice_read; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_notice_read (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    notice_id bigint NOT NULL,
    read_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: sys_notice_read_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_notice_read_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_notice_read_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_notice_read_id_seq OWNED BY public.sys_notice_read.id;


--
-- Name: sys_role; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_role (
    role_id bigint NOT NULL,
    role_name character varying(30) NOT NULL,
    role_key character varying(100) NOT NULL,
    role_sort integer NOT NULL,
    data_scope character varying(1) NOT NULL,
    menu_check_strictly boolean NOT NULL,
    dept_check_strictly boolean NOT NULL,
    status character varying(1) NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_by character varying(64),
    create_time timestamp without time zone,
    update_by character varying(64),
    update_time timestamp without time zone,
    remark character varying(500)
);


--
-- Name: sys_role_menu; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_role_menu (
    role_id bigint NOT NULL,
    menu_id bigint NOT NULL
);


--
-- Name: sys_role_role_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_role_role_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_role_role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_role_role_id_seq OWNED BY public.sys_role.role_id;


--
-- Name: sys_sensitive_word; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_sensitive_word (
    id bigint NOT NULL,
    word character varying(100) NOT NULL,
    level integer NOT NULL,
    status character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: sys_sensitive_word_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_sensitive_word_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_sensitive_word_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_sensitive_word_id_seq OWNED BY public.sys_sensitive_word.id;


--
-- Name: sys_user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_user (
    user_id bigint NOT NULL,
    user_name character varying(30) NOT NULL,
    nick_name character varying(30) NOT NULL,
    email character varying(50),
    phonenumber character varying(11),
    sex character varying(1) NOT NULL,
    avatar character varying(500),
    password character varying(100) NOT NULL,
    status character varying(1) NOT NULL,
    del_flag character varying(1) NOT NULL,
    login_ip character varying(128),
    login_date timestamp without time zone,
    dept_id bigint,
    create_by character varying(64),
    create_time timestamp without time zone,
    update_by character varying(64),
    update_time timestamp without time zone,
    remark character varying(500)
);


--
-- Name: sys_user_role; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sys_user_role (
    user_id bigint NOT NULL,
    role_id bigint NOT NULL
);


--
-- Name: sys_user_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sys_user_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sys_user_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sys_user_user_id_seq OWNED BY public.sys_user.user_id;


--
-- Name: user_bank_favorite; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_bank_favorite (
    favorite_id bigint NOT NULL,
    user_id bigint NOT NULL,
    bank_id bigint NOT NULL,
    notes character varying(200),
    tags character varying(100),
    sort_order integer NOT NULL,
    is_starred integer NOT NULL,
    last_study_time timestamp without time zone,
    study_count integer NOT NULL,
    favorite_status integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: user_bank_favorite_favorite_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_bank_favorite_favorite_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_bank_favorite_favorite_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_bank_favorite_favorite_id_seq OWNED BY public.user_bank_favorite.favorite_id;


--
-- Name: user_note_draft; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_note_draft (
    user_id bigint NOT NULL,
    title character varying(255),
    content text,
    markdown_content text,
    category_id bigint,
    tags character varying(500),
    is_public integer NOT NULL,
    public_section_id bigint,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: user_note_favorite; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_note_favorite (
    favorite_id bigint NOT NULL,
    user_id bigint NOT NULL,
    note_id bigint NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_note_favorite_favorite_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_note_favorite_favorite_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_note_favorite_favorite_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_note_favorite_favorite_id_seq OWNED BY public.user_note_favorite.favorite_id;


--
-- Name: user_notification; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_notification (
    notification_id bigint NOT NULL,
    user_id bigint NOT NULL,
    notify_type character varying(32) NOT NULL,
    title character varying(100) NOT NULL,
    content text,
    link character varying(255),
    is_read integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: user_notification_notification_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_notification_notification_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_notification_notification_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_notification_notification_id_seq OWNED BY public.user_notification.notification_id;


--
-- Name: user_practice_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_practice_log (
    log_id bigint NOT NULL,
    user_id bigint NOT NULL,
    question_id bigint NOT NULL,
    bank_id bigint,
    is_correct integer NOT NULL,
    answer text,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    client_token character varying(64)
);


--
-- Name: user_practice_log_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_practice_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_practice_log_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_practice_log_log_id_seq OWNED BY public.user_practice_log.log_id;


--
-- Name: user_question_error; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_question_error (
    error_id bigint NOT NULL,
    user_id bigint NOT NULL,
    question_id bigint NOT NULL,
    bank_id bigint NOT NULL,
    error_time timestamp without time zone DEFAULT now() NOT NULL,
    last_error_time timestamp without time zone DEFAULT now() NOT NULL,
    error_count integer NOT NULL,
    notes text,
    tags character varying(100),
    difficulty_rating integer,
    review_count integer NOT NULL,
    last_review_time timestamp without time zone,
    next_review_time timestamp without time zone,
    is_mastered integer NOT NULL,
    status integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: user_question_error_error_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_question_error_error_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_question_error_error_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_question_error_error_id_seq OWNED BY public.user_question_error.error_id;


--
-- Name: user_question_favorite; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_question_favorite (
    favorite_id bigint NOT NULL,
    user_id bigint NOT NULL,
    question_id bigint NOT NULL,
    bank_id bigint NOT NULL,
    notes text,
    tags character varying(100),
    difficulty_rating integer,
    error_times integer NOT NULL,
    correct_times integer NOT NULL,
    last_review_time timestamp without time zone,
    next_review_time timestamp without time zone,
    review_count integer NOT NULL,
    is_starred integer NOT NULL,
    favorite_status integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: user_question_favorite_favorite_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_question_favorite_favorite_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_question_favorite_favorite_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_question_favorite_favorite_id_seq OWNED BY public.user_question_favorite.favorite_id;


--
-- Name: user_question_marked; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_question_marked (
    marked_id bigint NOT NULL,
    user_id bigint NOT NULL,
    question_id bigint NOT NULL,
    bank_id bigint NOT NULL,
    notes text,
    tags character varying(100),
    marked_type integer NOT NULL,
    difficulty_level integer,
    error_times_before_mark integer NOT NULL,
    correct_times_before_mark integer NOT NULL,
    review_count integer NOT NULL,
    last_review_time timestamp without time zone,
    next_review_time timestamp without time zone,
    is_mastered integer NOT NULL,
    mastery_date timestamp without time zone,
    marked_status integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL,
    update_time timestamp without time zone
);


--
-- Name: user_question_marked_marked_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_question_marked_marked_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_question_marked_marked_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_question_marked_marked_id_seq OWNED BY public.user_question_marked.marked_id;


--
-- Name: word_books; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.word_books (
    book_id bigint NOT NULL,
    book_name character varying(255) NOT NULL,
    book_description text,
    word_count integer NOT NULL,
    cover_image character varying(500),
    status character varying(1) NOT NULL,
    del_flag character varying(1) NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: word_books_book_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.word_books_book_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: word_books_book_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.word_books_book_id_seq OWNED BY public.word_books.book_id;


--
-- Name: words; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.words (
    word_id bigint NOT NULL,
    book_id bigint NOT NULL,
    word character varying(100) NOT NULL,
    phonetic character varying(100),
    translation text,
    example text,
    audio_url character varying(500),
    sort_order integer NOT NULL,
    create_time timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: words_word_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.words_word_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: words_word_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.words_word_id_seq OWNED BY public.words.word_id;


--
-- Name: ai_agent_config id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_config ALTER COLUMN id SET DEFAULT nextval('public.ai_agent_config_id_seq'::regclass);


--
-- Name: ai_agent_memory id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_memory ALTER COLUMN id SET DEFAULT nextval('public.ai_agent_memory_id_seq'::regclass);


--
-- Name: ai_agent_op_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_op_log ALTER COLUMN id SET DEFAULT nextval('public.ai_agent_op_log_id_seq'::regclass);


--
-- Name: ai_agent_role_pref id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_role_pref ALTER COLUMN id SET DEFAULT nextval('public.ai_agent_role_pref_id_seq'::regclass);


--
-- Name: ai_agent_tool_pref id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_tool_pref ALTER COLUMN id SET DEFAULT nextval('public.ai_agent_tool_pref_id_seq'::regclass);


--
-- Name: ai_chat_message id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_chat_message ALTER COLUMN id SET DEFAULT nextval('public.ai_chat_message_id_seq'::regclass);


--
-- Name: bank_share id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_share ALTER COLUMN id SET DEFAULT nextval('public.bank_share_id_seq'::regclass);


--
-- Name: bank_share_receive id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_share_receive ALTER COLUMN id SET DEFAULT nextval('public.bank_share_receive_id_seq'::regclass);


--
-- Name: carousel id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carousel ALTER COLUMN id SET DEFAULT nextval('public.carousel_id_seq'::regclass);


--
-- Name: chat_message id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_message ALTER COLUMN id SET DEFAULT nextval('public.chat_message_id_seq'::regclass);


--
-- Name: courses course_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses ALTER COLUMN course_id SET DEFAULT nextval('public.courses_course_id_seq'::regclass);


--
-- Name: leave_message id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leave_message ALTER COLUMN id SET DEFAULT nextval('public.leave_message_id_seq'::regclass);


--
-- Name: note note_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note ALTER COLUMN note_id SET DEFAULT nextval('public.note_note_id_seq'::regclass);


--
-- Name: note_category id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_category ALTER COLUMN id SET DEFAULT nextval('public.note_category_id_seq'::regclass);


--
-- Name: note_comment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_comment ALTER COLUMN id SET DEFAULT nextval('public.note_comment_id_seq'::regclass);


--
-- Name: note_public_section id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_public_section ALTER COLUMN id SET DEFAULT nextval('public.note_public_section_id_seq'::regclass);


--
-- Name: note_question id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question ALTER COLUMN id SET DEFAULT nextval('public.note_question_id_seq'::regclass);


--
-- Name: note_question_bank id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question_bank ALTER COLUMN id SET DEFAULT nextval('public.note_question_bank_id_seq'::regclass);


--
-- Name: question_bank id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_bank ALTER COLUMN id SET DEFAULT nextval('public.question_bank_id_seq'::regclass);


--
-- Name: question_main id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_main ALTER COLUMN id SET DEFAULT nextval('public.question_main_id_seq'::regclass);


--
-- Name: question_sub id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_sub ALTER COLUMN id SET DEFAULT nextval('public.question_sub_id_seq'::regclass);


--
-- Name: rag_document id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document ALTER COLUMN id SET DEFAULT nextval('public.rag_document_id_seq'::regclass);


--
-- Name: rag_document_chunk id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunk ALTER COLUMN id SET DEFAULT nextval('public.rag_document_chunk_id_seq'::regclass);


--
-- Name: rag_knowledge_base id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_knowledge_base ALTER COLUMN id SET DEFAULT nextval('public.rag_knowledge_base_id_seq'::regclass);


--
-- Name: rag_qa_record id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_qa_record ALTER COLUMN id SET DEFAULT nextval('public.rag_qa_record_id_seq'::regclass);


--
-- Name: sys_ai_config config_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_ai_config ALTER COLUMN config_id SET DEFAULT nextval('public.sys_ai_config_config_id_seq'::regclass);


--
-- Name: sys_config config_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_config ALTER COLUMN config_id SET DEFAULT nextval('public.sys_config_config_id_seq'::regclass);


--
-- Name: sys_dept dept_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_dept ALTER COLUMN dept_id SET DEFAULT nextval('public.sys_dept_dept_id_seq'::regclass);


--
-- Name: sys_menu menu_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_menu ALTER COLUMN menu_id SET DEFAULT nextval('public.sys_menu_menu_id_seq'::regclass);


--
-- Name: sys_notice notice_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice ALTER COLUMN notice_id SET DEFAULT nextval('public.sys_notice_notice_id_seq'::regclass);


--
-- Name: sys_notice_delete id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_delete ALTER COLUMN id SET DEFAULT nextval('public.sys_notice_delete_id_seq'::regclass);


--
-- Name: sys_notice_read id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_read ALTER COLUMN id SET DEFAULT nextval('public.sys_notice_read_id_seq'::regclass);


--
-- Name: sys_role role_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_role ALTER COLUMN role_id SET DEFAULT nextval('public.sys_role_role_id_seq'::regclass);


--
-- Name: sys_sensitive_word id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_sensitive_word ALTER COLUMN id SET DEFAULT nextval('public.sys_sensitive_word_id_seq'::regclass);


--
-- Name: sys_user user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user ALTER COLUMN user_id SET DEFAULT nextval('public.sys_user_user_id_seq'::regclass);


--
-- Name: user_bank_favorite favorite_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_bank_favorite ALTER COLUMN favorite_id SET DEFAULT nextval('public.user_bank_favorite_favorite_id_seq'::regclass);


--
-- Name: user_note_favorite favorite_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_favorite ALTER COLUMN favorite_id SET DEFAULT nextval('public.user_note_favorite_favorite_id_seq'::regclass);


--
-- Name: user_notification notification_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notification ALTER COLUMN notification_id SET DEFAULT nextval('public.user_notification_notification_id_seq'::regclass);


--
-- Name: user_practice_log log_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_practice_log ALTER COLUMN log_id SET DEFAULT nextval('public.user_practice_log_log_id_seq'::regclass);


--
-- Name: user_question_error error_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_error ALTER COLUMN error_id SET DEFAULT nextval('public.user_question_error_error_id_seq'::regclass);


--
-- Name: user_question_favorite favorite_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_favorite ALTER COLUMN favorite_id SET DEFAULT nextval('public.user_question_favorite_favorite_id_seq'::regclass);


--
-- Name: user_question_marked marked_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_marked ALTER COLUMN marked_id SET DEFAULT nextval('public.user_question_marked_marked_id_seq'::regclass);


--
-- Name: word_books book_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.word_books ALTER COLUMN book_id SET DEFAULT nextval('public.word_books_book_id_seq'::regclass);


--
-- Name: words word_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.words ALTER COLUMN word_id SET DEFAULT nextval('public.words_word_id_seq'::regclass);


--
-- Name: ai_agent_config ai_agent_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_config
    ADD CONSTRAINT ai_agent_config_pkey PRIMARY KEY (id);


--
-- Name: ai_agent_memory ai_agent_memory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_memory
    ADD CONSTRAINT ai_agent_memory_pkey PRIMARY KEY (id);


--
-- Name: ai_agent_op_log ai_agent_op_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_op_log
    ADD CONSTRAINT ai_agent_op_log_pkey PRIMARY KEY (id);


--
-- Name: ai_agent_role_pref ai_agent_role_pref_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_role_pref
    ADD CONSTRAINT ai_agent_role_pref_pkey PRIMARY KEY (id);


--
-- Name: ai_agent_timeline ai_agent_timeline_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_timeline
    ADD CONSTRAINT ai_agent_timeline_pkey PRIMARY KEY (session_id);


--
-- Name: ai_agent_tool_pref ai_agent_tool_pref_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_tool_pref
    ADD CONSTRAINT ai_agent_tool_pref_pkey PRIMARY KEY (id);


--
-- Name: ai_chat_message ai_chat_message_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_chat_message
    ADD CONSTRAINT ai_chat_message_pkey PRIMARY KEY (id);


--
-- Name: ai_chat_session ai_chat_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_chat_session
    ADD CONSTRAINT ai_chat_session_pkey PRIMARY KEY (session_id);


--
-- Name: bank_share bank_share_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_share
    ADD CONSTRAINT bank_share_pkey PRIMARY KEY (id);


--
-- Name: bank_share_receive bank_share_receive_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_share_receive
    ADD CONSTRAINT bank_share_receive_pkey PRIMARY KEY (id);


--
-- Name: bank_share bank_share_share_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_share
    ADD CONSTRAINT bank_share_share_token_key UNIQUE (share_token);


--
-- Name: carousel carousel_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carousel
    ADD CONSTRAINT carousel_pkey PRIMARY KEY (id);


--
-- Name: chat_message chat_message_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_message
    ADD CONSTRAINT chat_message_pkey PRIMARY KEY (id);


--
-- Name: courses courses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (course_id);


--
-- Name: leave_message leave_message_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leave_message
    ADD CONSTRAINT leave_message_pkey PRIMARY KEY (id);


--
-- Name: note_category note_category_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_category
    ADD CONSTRAINT note_category_pkey PRIMARY KEY (id);


--
-- Name: note_comment note_comment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_comment
    ADD CONSTRAINT note_comment_pkey PRIMARY KEY (id);


--
-- Name: note note_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note
    ADD CONSTRAINT note_pkey PRIMARY KEY (note_id);


--
-- Name: note_public_section note_public_section_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_public_section
    ADD CONSTRAINT note_public_section_pkey PRIMARY KEY (id);


--
-- Name: note_question_bank note_question_bank_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question_bank
    ADD CONSTRAINT note_question_bank_pkey PRIMARY KEY (id);


--
-- Name: note_question note_question_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question
    ADD CONSTRAINT note_question_pkey PRIMARY KEY (id);


--
-- Name: question_bank question_bank_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_bank
    ADD CONSTRAINT question_bank_pkey PRIMARY KEY (id);


--
-- Name: question_main question_main_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_main
    ADD CONSTRAINT question_main_pkey PRIMARY KEY (id);


--
-- Name: question_sub question_sub_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_sub
    ADD CONSTRAINT question_sub_pkey PRIMARY KEY (id);


--
-- Name: rag_document_chunk rag_document_chunk_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunk
    ADD CONSTRAINT rag_document_chunk_pkey PRIMARY KEY (id);


--
-- Name: rag_document rag_document_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document
    ADD CONSTRAINT rag_document_pkey PRIMARY KEY (id);


--
-- Name: rag_knowledge_base rag_knowledge_base_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_knowledge_base
    ADD CONSTRAINT rag_knowledge_base_pkey PRIMARY KEY (id);


--
-- Name: rag_qa_record rag_qa_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_qa_record
    ADD CONSTRAINT rag_qa_record_pkey PRIMARY KEY (id);


--
-- Name: sys_ai_config sys_ai_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_ai_config
    ADD CONSTRAINT sys_ai_config_pkey PRIMARY KEY (config_id);


--
-- Name: sys_config sys_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_config
    ADD CONSTRAINT sys_config_pkey PRIMARY KEY (config_id);


--
-- Name: sys_dept sys_dept_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_dept
    ADD CONSTRAINT sys_dept_pkey PRIMARY KEY (dept_id);


--
-- Name: sys_menu sys_menu_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_menu
    ADD CONSTRAINT sys_menu_pkey PRIMARY KEY (menu_id);


--
-- Name: sys_notice_delete sys_notice_delete_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_delete
    ADD CONSTRAINT sys_notice_delete_pkey PRIMARY KEY (id);


--
-- Name: sys_notice sys_notice_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice
    ADD CONSTRAINT sys_notice_pkey PRIMARY KEY (notice_id);


--
-- Name: sys_notice_read sys_notice_read_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_read
    ADD CONSTRAINT sys_notice_read_pkey PRIMARY KEY (id);


--
-- Name: sys_role_menu sys_role_menu_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_role_menu
    ADD CONSTRAINT sys_role_menu_pkey PRIMARY KEY (role_id, menu_id);


--
-- Name: sys_role sys_role_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_role
    ADD CONSTRAINT sys_role_pkey PRIMARY KEY (role_id);


--
-- Name: sys_sensitive_word sys_sensitive_word_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_sensitive_word
    ADD CONSTRAINT sys_sensitive_word_pkey PRIMARY KEY (id);


--
-- Name: sys_sensitive_word sys_sensitive_word_word_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_sensitive_word
    ADD CONSTRAINT sys_sensitive_word_word_key UNIQUE (word);


--
-- Name: sys_user sys_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_pkey PRIMARY KEY (user_id);


--
-- Name: sys_user_role sys_user_role_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user_role
    ADD CONSTRAINT sys_user_role_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: sys_user sys_user_user_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_user_name_key UNIQUE (user_name);


--
-- Name: note_question_bank uk_note_bank; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question_bank
    ADD CONSTRAINT uk_note_bank UNIQUE (note_id, question_bank_id);


--
-- Name: note_question uk_note_question; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question
    ADD CONSTRAINT uk_note_question UNIQUE (note_id, question_id);


--
-- Name: rag_document_chunk uk_rag_chunk_doc_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunk
    ADD CONSTRAINT uk_rag_chunk_doc_index UNIQUE (doc_id, chunk_index);


--
-- Name: bank_share_receive uk_share_receiver; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_share_receive
    ADD CONSTRAINT uk_share_receiver UNIQUE (share_id, receiver_id);


--
-- Name: user_question_error uk_uq_error; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_error
    ADD CONSTRAINT uk_uq_error UNIQUE (user_id, question_id);


--
-- Name: user_question_favorite uk_uq_favorite; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_favorite
    ADD CONSTRAINT uk_uq_favorite UNIQUE (user_id, question_id);


--
-- Name: user_question_marked uk_uq_marked; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_marked
    ADD CONSTRAINT uk_uq_marked UNIQUE (user_id, question_id);


--
-- Name: user_bank_favorite uk_user_bank; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_bank_favorite
    ADD CONSTRAINT uk_user_bank UNIQUE (user_id, bank_id);


--
-- Name: user_note_favorite uk_user_note_favorite; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_favorite
    ADD CONSTRAINT uk_user_note_favorite UNIQUE (user_id, note_id);


--
-- Name: sys_notice_read uk_user_notice; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_read
    ADD CONSTRAINT uk_user_notice UNIQUE (user_id, notice_id);


--
-- Name: sys_notice_delete uk_user_notice_delete; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_delete
    ADD CONSTRAINT uk_user_notice_delete UNIQUE (user_id, notice_id);


--
-- Name: user_bank_favorite user_bank_favorite_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_bank_favorite
    ADD CONSTRAINT user_bank_favorite_pkey PRIMARY KEY (favorite_id);


--
-- Name: user_note_draft user_note_draft_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_draft
    ADD CONSTRAINT user_note_draft_pkey PRIMARY KEY (user_id);


--
-- Name: user_note_favorite user_note_favorite_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_favorite
    ADD CONSTRAINT user_note_favorite_pkey PRIMARY KEY (favorite_id);


--
-- Name: user_notification user_notification_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notification
    ADD CONSTRAINT user_notification_pkey PRIMARY KEY (notification_id);


--
-- Name: user_practice_log user_practice_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_practice_log
    ADD CONSTRAINT user_practice_log_pkey PRIMARY KEY (log_id);


--
-- Name: user_question_error user_question_error_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_error
    ADD CONSTRAINT user_question_error_pkey PRIMARY KEY (error_id);


--
-- Name: user_question_favorite user_question_favorite_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_favorite
    ADD CONSTRAINT user_question_favorite_pkey PRIMARY KEY (favorite_id);


--
-- Name: user_question_marked user_question_marked_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_marked
    ADD CONSTRAINT user_question_marked_pkey PRIMARY KEY (marked_id);


--
-- Name: word_books word_books_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.word_books
    ADD CONSTRAINT word_books_pkey PRIMARY KEY (book_id);


--
-- Name: words words_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.words
    ADD CONSTRAINT words_pkey PRIMARY KEY (word_id);


--
-- Name: idx_agent_memory_user_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_memory_user_type ON public.ai_agent_memory USING btree (user_id, memory_type, create_time);


--
-- Name: idx_ai_agent_op_log_turn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_agent_op_log_turn ON public.ai_agent_op_log USING btree (user_id, session_id, turn_id);


--
-- Name: idx_ai_agent_timeline_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_agent_timeline_user ON public.ai_agent_timeline USING btree (user_id, update_time);


--
-- Name: idx_ai_chat_msg_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_chat_msg_session ON public.ai_chat_message USING btree (session_id, id);


--
-- Name: idx_ai_chat_msg_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_chat_msg_user ON public.ai_chat_message USING btree (user_id, id);


--
-- Name: idx_ai_chat_session_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_chat_session_user ON public.ai_chat_session USING btree (user_id, update_time);


--
-- Name: idx_practice_user_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_practice_user_question ON public.user_practice_log USING btree (user_id, question_id);


--
-- Name: idx_practice_user_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_practice_user_time ON public.user_practice_log USING btree (user_id, create_time);


--
-- Name: idx_rag_chunk_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunk_doc ON public.rag_document_chunk USING btree (doc_id);


--
-- Name: idx_rag_chunk_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunk_embedding ON public.rag_document_chunk USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_rag_chunk_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunk_fts ON public.rag_document_chunk USING gin (search_vec);


--
-- Name: idx_rag_chunk_kb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunk_kb ON public.rag_document_chunk USING btree (kb_id);


--
-- Name: idx_rag_chunk_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_chunk_trgm ON public.rag_document_chunk USING gin (content public.gin_trgm_ops);


--
-- Name: idx_rag_doc_kb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_doc_kb ON public.rag_document USING btree (kb_id);


--
-- Name: idx_rag_doc_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_doc_user ON public.rag_document USING btree (user_id);


--
-- Name: idx_rag_qa_kb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_qa_kb ON public.rag_qa_record USING btree (kb_id);


--
-- Name: idx_rag_qa_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rag_qa_user ON public.rag_qa_record USING btree (user_id);


--
-- Name: ix_ai_agent_timeline_update_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_agent_timeline_update_time ON public.ai_agent_timeline USING btree (update_time);


--
-- Name: ix_ai_chat_session_update_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_chat_session_update_time ON public.ai_chat_session USING btree (update_time);


--
-- Name: ix_bank_share_bank_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bank_share_bank_id ON public.bank_share USING btree (bank_id);


--
-- Name: ix_bank_share_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bank_share_owner_id ON public.bank_share USING btree (owner_id);


--
-- Name: ix_bank_share_receive_bank_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bank_share_receive_bank_id ON public.bank_share_receive USING btree (bank_id);


--
-- Name: ix_bank_share_receive_receiver_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bank_share_receive_receiver_id ON public.bank_share_receive USING btree (receiver_id);


--
-- Name: ix_bank_share_receive_share_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bank_share_receive_share_id ON public.bank_share_receive USING btree (share_id);


--
-- Name: ix_bank_share_share_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bank_share_share_code ON public.bank_share USING btree (share_code);


--
-- Name: ix_user_notification_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_notification_user_id ON public.user_notification USING btree (user_id);


--
-- Name: uk_ai_agent_config_user_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uk_ai_agent_config_user_name ON public.ai_agent_config USING btree (user_id, name);


--
-- Name: uk_ai_agent_role_pref_user_role; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uk_ai_agent_role_pref_user_role ON public.ai_agent_role_pref USING btree (user_id, role_key);


--
-- Name: uk_ai_agent_tool_pref_user_tool; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uk_ai_agent_tool_pref_user_tool ON public.ai_agent_tool_pref USING btree (user_id, tool_name);


--
-- Name: uk_practice_client_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uk_practice_client_token ON public.user_practice_log USING btree (client_token);


--
-- Name: ai_agent_memory ai_agent_memory_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agent_memory
    ADD CONSTRAINT ai_agent_memory_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: courses courses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: note note_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note
    ADD CONSTRAINT note_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.note_category(id);


--
-- Name: note_category note_category_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_category
    ADD CONSTRAINT note_category_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: note_comment note_comment_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_comment
    ADD CONSTRAINT note_comment_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.note(note_id);


--
-- Name: note_comment note_comment_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_comment
    ADD CONSTRAINT note_comment_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: note_question_bank note_question_bank_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question_bank
    ADD CONSTRAINT note_question_bank_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.note(note_id);


--
-- Name: note_question_bank note_question_bank_question_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question_bank
    ADD CONSTRAINT note_question_bank_question_bank_id_fkey FOREIGN KEY (question_bank_id) REFERENCES public.question_bank(id);


--
-- Name: note_question note_question_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question
    ADD CONSTRAINT note_question_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.note(note_id);


--
-- Name: note_question note_question_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note_question
    ADD CONSTRAINT note_question_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question_main(id);


--
-- Name: note note_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.note
    ADD CONSTRAINT note_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: question_main question_main_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_main
    ADD CONSTRAINT question_main_bank_id_fkey FOREIGN KEY (bank_id) REFERENCES public.question_bank(id);


--
-- Name: question_sub question_sub_main_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_sub
    ADD CONSTRAINT question_sub_main_id_fkey FOREIGN KEY (main_id) REFERENCES public.question_main(id);


--
-- Name: rag_document_chunk rag_document_chunk_doc_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunk
    ADD CONSTRAINT rag_document_chunk_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.rag_document(id);


--
-- Name: rag_document_chunk rag_document_chunk_kb_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document_chunk
    ADD CONSTRAINT rag_document_chunk_kb_id_fkey FOREIGN KEY (kb_id) REFERENCES public.rag_knowledge_base(id);


--
-- Name: rag_document rag_document_kb_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document
    ADD CONSTRAINT rag_document_kb_id_fkey FOREIGN KEY (kb_id) REFERENCES public.rag_knowledge_base(id);


--
-- Name: rag_document rag_document_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_document
    ADD CONSTRAINT rag_document_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: rag_knowledge_base rag_knowledge_base_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_knowledge_base
    ADD CONSTRAINT rag_knowledge_base_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: rag_qa_record rag_qa_record_kb_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_qa_record
    ADD CONSTRAINT rag_qa_record_kb_id_fkey FOREIGN KEY (kb_id) REFERENCES public.rag_knowledge_base(id);


--
-- Name: rag_qa_record rag_qa_record_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rag_qa_record
    ADD CONSTRAINT rag_qa_record_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: sys_notice_delete sys_notice_delete_notice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_delete
    ADD CONSTRAINT sys_notice_delete_notice_id_fkey FOREIGN KEY (notice_id) REFERENCES public.sys_notice(notice_id);


--
-- Name: sys_notice_delete sys_notice_delete_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_delete
    ADD CONSTRAINT sys_notice_delete_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: sys_notice_read sys_notice_read_notice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_read
    ADD CONSTRAINT sys_notice_read_notice_id_fkey FOREIGN KEY (notice_id) REFERENCES public.sys_notice(notice_id);


--
-- Name: sys_notice_read sys_notice_read_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_notice_read
    ADD CONSTRAINT sys_notice_read_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: sys_role_menu sys_role_menu_menu_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_role_menu
    ADD CONSTRAINT sys_role_menu_menu_id_fkey FOREIGN KEY (menu_id) REFERENCES public.sys_menu(menu_id);


--
-- Name: sys_role_menu sys_role_menu_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_role_menu
    ADD CONSTRAINT sys_role_menu_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.sys_role(role_id);


--
-- Name: sys_user sys_user_dept_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user
    ADD CONSTRAINT sys_user_dept_id_fkey FOREIGN KEY (dept_id) REFERENCES public.sys_dept(dept_id);


--
-- Name: sys_user_role sys_user_role_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user_role
    ADD CONSTRAINT sys_user_role_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.sys_role(role_id);


--
-- Name: sys_user_role sys_user_role_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sys_user_role
    ADD CONSTRAINT sys_user_role_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: user_bank_favorite user_bank_favorite_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_bank_favorite
    ADD CONSTRAINT user_bank_favorite_bank_id_fkey FOREIGN KEY (bank_id) REFERENCES public.question_bank(id);


--
-- Name: user_bank_favorite user_bank_favorite_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_bank_favorite
    ADD CONSTRAINT user_bank_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: user_note_draft user_note_draft_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_draft
    ADD CONSTRAINT user_note_draft_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: user_note_favorite user_note_favorite_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_favorite
    ADD CONSTRAINT user_note_favorite_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.note(note_id);


--
-- Name: user_note_favorite user_note_favorite_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_note_favorite
    ADD CONSTRAINT user_note_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: user_question_error user_question_error_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_error
    ADD CONSTRAINT user_question_error_bank_id_fkey FOREIGN KEY (bank_id) REFERENCES public.question_bank(id);


--
-- Name: user_question_error user_question_error_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_error
    ADD CONSTRAINT user_question_error_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question_main(id);


--
-- Name: user_question_error user_question_error_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_error
    ADD CONSTRAINT user_question_error_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: user_question_favorite user_question_favorite_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_favorite
    ADD CONSTRAINT user_question_favorite_bank_id_fkey FOREIGN KEY (bank_id) REFERENCES public.question_bank(id);


--
-- Name: user_question_favorite user_question_favorite_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_favorite
    ADD CONSTRAINT user_question_favorite_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question_main(id);


--
-- Name: user_question_favorite user_question_favorite_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_favorite
    ADD CONSTRAINT user_question_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: user_question_marked user_question_marked_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_marked
    ADD CONSTRAINT user_question_marked_bank_id_fkey FOREIGN KEY (bank_id) REFERENCES public.question_bank(id);


--
-- Name: user_question_marked user_question_marked_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_marked
    ADD CONSTRAINT user_question_marked_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.question_main(id);


--
-- Name: user_question_marked user_question_marked_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_question_marked
    ADD CONSTRAINT user_question_marked_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.sys_user(user_id);


--
-- Name: words words_book_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.words
    ADD CONSTRAINT words_book_id_fkey FOREIGN KEY (book_id) REFERENCES public.word_books(book_id);


-- ============================================================
-- ② 基础字典 / 权限种子（部门 / 角色 / 菜单 / 系统参数）
-- ============================================================
--
-- Data for Name: sys_config; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (1, '主框架页-默认皮肤样式名称', 'sys.index.skinName', 'skin-blue', 'Y', 'admin', '2025-10-23 20:06:49', '', NULL, '蓝色 skin-blue、绿色 skin-green、紫色 skin-purple、红色 skin-red、黄色 skin-yellow');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (2, '用户管理-账号初始密码', 'sys.user.initPassword', '123456', 'Y', 'admin', '2025-10-23 20:06:49', '', NULL, '初始化密码 123456');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (3, '主框架页-侧边栏主题', 'sys.index.sideTheme', 'theme-dark', 'Y', 'admin', '2025-10-23 20:06:49', '', NULL, '深色主题theme-dark，浅色主题theme-light');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (4, '账号自助-验证码开关', 'sys.account.captchaEnabled', 'false', 'Y', 'admin', '2025-10-23 20:06:49', 'admin', '2025-10-24 23:01:28', '是否开启验证码功能（true开启，false关闭）');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (5, '账号自助-是否开启用户注册功能', 'sys.account.registerUser', 'true', 'Y', 'admin', '2025-10-23 20:06:49', 'admin', '2025-12-03 20:01:22', '是否开启注册用户功能（true开启，false关闭）');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (6, '用户登录-黑名单列表', 'sys.login.blackIPList', '', 'Y', 'admin', '2025-10-23 20:06:49', '', NULL, '设置登录IP黑名单限制，多个匹配项以;分隔，支持匹配（*通配、网段）');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (7, '用户管理-初始密码修改策略', 'sys.account.initPasswordModify', '1', 'Y', 'admin', '2025-10-23 20:06:49', '', NULL, '0：初始密码修改策略关闭，没有任何提示，1：提醒用户，如果未修改初始密码，则在登录时就会提醒修改密码对话框');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (8, '用户管理-账号密码更新周期', 'sys.account.passwordValidateDays', '0', 'Y', 'admin', '2025-10-23 20:06:49', '', NULL, '密码更新周期（填写数字，数据初始化值为0不限制，若修改必须为大于0小于365的正整数），如果超过这个周期登录系统时，则在登录时就会提醒修改密码对话框');
INSERT INTO public.sys_config (config_id, config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark) VALUES (9, '系统-演示模式', 'sys.demo.mode', 'true', 'Y', 'admin', now(), '', NULL, '演示模式：true=登录页显示「演示账号一键登录」入口（自用/演示）；false=上线体验版，直接走账号密码登录/注册，不暴露演示账号');


--
-- Data for Name: sys_dept; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (100, 0, '0', '若依科技', 0, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (101, 100, '0,100', '深圳总公司', 1, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (102, 100, '0,100', '长沙分公司', 2, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (103, 101, '0,100,101', '研发部门', 1, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (104, 101, '0,100,101', '市场部门', 2, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (105, 101, '0,100,101', '测试部门', 3, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (106, 101, '0,100,101', '财务部门', 4, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (107, 101, '0,100,101', '运维部门', 5, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (108, 102, '0,100,102', '市场部门', 1, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);
INSERT INTO public.sys_dept (dept_id, parent_id, ancestors, dept_name, order_num, leader, phone, email, status, del_flag, create_time, update_time) VALUES (109, 102, '0,100,102', '财务部门', 2, '若依', '15888888888', 'ry@qq.com', '0', '0', '2025-10-23 20:06:49', NULL);


--
-- Data for Name: sys_role; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.sys_role (role_id, role_name, role_key, role_sort, data_scope, menu_check_strictly, dept_check_strictly, status, del_flag, create_by, create_time, update_by, update_time, remark) VALUES (1, '超级管理员', 'admin', 1, '1', true, true, '0', '0', 'admin', '2025-10-23 20:06:49', '', NULL, '超级管理员');
INSERT INTO public.sys_role (role_id, role_name, role_key, role_sort, data_scope, menu_check_strictly, dept_check_strictly, status, del_flag, create_by, create_time, update_by, update_time, remark) VALUES (2, '普通角色', 'common', 2, '2', true, true, '0', '0', 'admin', '2025-10-23 20:06:49', 'admin', '2025-12-20 08:12:26', '普通角色');
INSERT INTO public.sys_role (role_id, role_name, role_key, role_sort, data_scope, menu_check_strictly, dept_check_strictly, status, del_flag, create_by, create_time, update_by, update_time, remark) VALUES (100, '游客', 'visitor', 3, '1', true, true, '0', '0', 'admin', '2026-04-27 20:17:18', '', NULL, NULL);


--
-- Name: sys_config_config_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sys_config_config_id_seq', 8, true);


--
-- Name: sys_dept_dept_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sys_dept_dept_id_seq', 109, true);


--
-- Name: sys_role_role_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sys_role_role_id_seq', 100, true);

--
-- Data for Name: sys_menu; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1, '系统管理', 0, 1, 'system', NULL, '', 1, 0, 'M', '0', '0', '', 'system', 'admin', '2025-10-23 20:06:49', '', NULL, '系统管理目录');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2, '系统监控', 0, 2, 'monitor', NULL, '', 1, 0, 'M', '0', '0', '', 'monitor', 'admin', '2025-10-23 20:06:49', 'admin', '2026-06-16 23:11:32', '系统监控目录');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (100, '用户管理', 1, 1, 'user', 'system/user/index', '', 1, 0, 'C', '0', '0', 'system:user:list', 'user', 'admin', '2025-10-23 20:06:49', '', NULL, '用户管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (101, '角色管理', 1, 2, 'role', 'system/role/index', '', 1, 0, 'C', '0', '0', 'system:role:list', 'peoples', 'admin', '2025-10-23 20:06:49', '', NULL, '角色管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (102, '菜单管理', 1, 3, 'menu', 'system/menu/index', '', 1, 0, 'C', '0', '0', 'system:menu:list', 'tree-table', 'admin', '2025-10-23 20:06:49', '', NULL, '菜单管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (105, '字典管理', 1, 6, 'dict', 'system/dict/index', '', 1, 0, 'C', '0', '0', 'system:dict:list', 'dict', 'admin', '2025-10-23 20:06:49', '', NULL, '字典管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (106, '参数设置', 1, 7, 'config', 'system/config/index', '', 1, 0, 'C', '0', '0', 'system:config:list', 'edit', 'admin', '2025-10-23 20:06:49', '', NULL, '参数设置菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (107, '通知公告', 0, 0, 'notice', 'system/notice/index', '', 1, 0, 'C', '0', '0', 'system:notice:list', 'message', 'admin', '2025-10-23 20:06:49', 'admin', '2026-04-29 19:31:07', '通知公告菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (108, '日志管理', 1, 9, 'log', '', '', 1, 0, 'M', '0', '0', '', 'log', 'admin', '2025-10-23 20:06:49', '', NULL, '日志管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (109, '在线用户', 2, 1, 'online', 'monitor/online/index', '', 1, 0, 'C', '0', '0', 'monitor:online:list', 'online', 'admin', '2025-10-23 20:06:49', '', NULL, '在线用户菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (110, '定时任务', 2, 2, 'job', 'monitor/job/index', '', 1, 0, 'C', '0', '0', 'monitor:job:list', 'job', 'admin', '2025-10-23 20:06:49', '', NULL, '定时任务菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (111, '数据监控', 2, 3, 'druid', 'monitor/druid/index', '', 1, 0, 'C', '0', '0', 'monitor:druid:list', 'druid', 'admin', '2025-10-23 20:06:49', '', NULL, '数据监控菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (112, '服务监控', 2, 4, 'server', 'monitor/server/index', '', 1, 0, 'C', '0', '0', 'monitor:server:list', 'server', 'admin', '2025-10-23 20:06:49', '', NULL, '服务监控菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (113, '缓存监控', 2, 5, 'cache', 'monitor/cache/index', '', 1, 0, 'C', '0', '0', 'monitor:cache:list', 'redis', 'admin', '2025-10-23 20:06:49', '', NULL, '缓存监控菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (114, '缓存列表', 2, 6, 'cacheList', 'monitor/cache/list', '', 1, 0, 'C', '0', '0', 'monitor:cache:list', 'redis-list', 'admin', '2025-10-23 20:06:49', '', NULL, '缓存列表菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (500, '操作日志', 108, 1, 'operlog', 'monitor/operlog/index', '', 1, 0, 'C', '0', '0', 'monitor:operlog:list', 'form', 'admin', '2025-10-23 20:06:49', '', NULL, '操作日志菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (501, '登录日志', 108, 2, 'logininfor', 'monitor/logininfor/index', '', 1, 0, 'C', '0', '0', 'monitor:logininfor:list', 'logininfor', 'admin', '2025-10-23 20:06:49', '', NULL, '登录日志菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1000, '用户查询', 100, 1, '', '', '', 1, 0, 'F', '0', '0', 'system:user:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1001, '用户新增', 100, 2, '', '', '', 1, 0, 'F', '0', '0', 'system:user:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1002, '用户修改', 100, 3, '', '', '', 1, 0, 'F', '0', '0', 'system:user:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1003, '用户删除', 100, 4, '', '', '', 1, 0, 'F', '0', '0', 'system:user:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1004, '用户导出', 100, 5, '', '', '', 1, 0, 'F', '0', '0', 'system:user:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1005, '用户导入', 100, 6, '', '', '', 1, 0, 'F', '0', '0', 'system:user:import', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1006, '重置密码', 100, 7, '', '', '', 1, 0, 'F', '0', '0', 'system:user:resetPwd', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1007, '角色查询', 101, 1, '', '', '', 1, 0, 'F', '0', '0', 'system:role:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1008, '角色新增', 101, 2, '', '', '', 1, 0, 'F', '0', '0', 'system:role:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1009, '角色修改', 101, 3, '', '', '', 1, 0, 'F', '0', '0', 'system:role:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1010, '角色删除', 101, 4, '', '', '', 1, 0, 'F', '0', '0', 'system:role:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1011, '角色导出', 101, 5, '', '', '', 1, 0, 'F', '0', '0', 'system:role:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1012, '菜单查询', 102, 1, '', '', '', 1, 0, 'F', '0', '0', 'system:menu:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1013, '菜单新增', 102, 2, '', '', '', 1, 0, 'F', '0', '0', 'system:menu:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1014, '菜单修改', 102, 3, '', '', '', 1, 0, 'F', '0', '0', 'system:menu:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1015, '菜单删除', 102, 4, '', '', '', 1, 0, 'F', '0', '0', 'system:menu:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1025, '字典查询', 105, 1, '#', '', '', 1, 0, 'F', '0', '0', 'system:dict:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1026, '字典新增', 105, 2, '#', '', '', 1, 0, 'F', '0', '0', 'system:dict:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1027, '字典修改', 105, 3, '#', '', '', 1, 0, 'F', '0', '0', 'system:dict:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1028, '字典删除', 105, 4, '#', '', '', 1, 0, 'F', '0', '0', 'system:dict:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1029, '字典导出', 105, 5, '#', '', '', 1, 0, 'F', '0', '0', 'system:dict:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1030, '参数查询', 106, 1, '#', '', '', 1, 0, 'F', '0', '0', 'system:config:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1031, '参数新增', 106, 2, '#', '', '', 1, 0, 'F', '0', '0', 'system:config:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1032, '参数修改', 106, 3, '#', '', '', 1, 0, 'F', '0', '0', 'system:config:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1033, '参数删除', 106, 4, '#', '', '', 1, 0, 'F', '0', '0', 'system:config:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1034, '参数导出', 106, 5, '#', '', '', 1, 0, 'F', '0', '0', 'system:config:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1035, '公告查询', 107, 1, '#', '', '', 1, 0, 'F', '0', '0', 'system:notice:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1036, '公告新增', 107, 2, '#', '', '', 1, 0, 'F', '0', '0', 'system:notice:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1037, '公告修改', 107, 3, '#', '', '', 1, 0, 'F', '0', '0', 'system:notice:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1038, '公告删除', 107, 4, '#', '', '', 1, 0, 'F', '0', '0', 'system:notice:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1039, '操作查询', 500, 1, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:operlog:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1040, '操作删除', 500, 2, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:operlog:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1041, '日志导出', 500, 3, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:operlog:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1042, '登录查询', 501, 1, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1043, '登录删除', 501, 2, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1044, '日志导出', 501, 3, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1045, '账户解锁', 501, 4, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:logininfor:unlock', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1046, '在线查询', 109, 1, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:online:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1047, '批量强退', 109, 2, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:online:batchLogout', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1048, '单条强退', 109, 3, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:online:forceLogout', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1049, '任务查询', 110, 1, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:job:query', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1050, '任务新增', 110, 2, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:job:add', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1051, '任务修改', 110, 3, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:job:edit', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1052, '任务删除', 110, 4, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:job:remove', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1053, '状态修改', 110, 5, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:job:changeStatus', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (1054, '任务导出', 110, 6, '#', '', '', 1, 0, 'F', '0', '0', 'monitor:job:export', '#', 'admin', '2025-10-23 20:06:49', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2006, '单词本', 0, 1, 'wordBooks', 'wordBooks/wordBooks/index', NULL, 1, 0, 'C', '0', '0', 'wordBooks:wordBooks:list', '#', 'admin', '2025-10-24 23:23:41', 'admin', '2025-10-24 23:25:42', '单词本菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2007, '单词本查询', 2006, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'wordBooks:wordBooks:query', '#', 'admin', '2025-10-24 23:23:41', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2008, '单词本新增', 2006, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'wordBooks:wordBooks:add', '#', 'admin', '2025-10-24 23:23:41', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2009, '单词本修改', 2006, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'wordBooks:wordBooks:edit', '#', 'admin', '2025-10-24 23:23:41', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2010, '单词本删除', 2006, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'wordBooks:wordBooks:remove', '#', 'admin', '2025-10-24 23:23:41', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2011, '单词本导出', 2006, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'wordBooks:wordBooks:export', '#', 'admin', '2025-10-24 23:23:41', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2012, '单词', 0, 1, 'words', 'words/words/index', NULL, 1, 0, 'C', '0', '0', 'words:words:list', '#', 'admin', '2025-10-24 23:27:16', 'admin', '2025-10-24 23:28:48', '单词菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2013, '单词查询', 2012, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'words:words:query', '#', 'admin', '2025-10-24 23:27:16', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2014, '单词新增', 2012, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'words:words:add', '#', 'admin', '2025-10-24 23:27:16', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2015, '单词修改', 2012, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'words:words:edit', '#', 'admin', '2025-10-24 23:27:16', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2016, '单词删除', 2012, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'words:words:remove', '#', 'admin', '2025-10-24 23:27:16', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2017, '单词导出', 2012, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'words:words:export', '#', 'admin', '2025-10-24 23:27:16', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2018, '单词练习', 0, 1, 'dictation', 'dictation/dictation/index', NULL, 1, 0, 'C', '0', '0', '', '#', 'admin', '2025-10-24 23:35:54', 'admin', '2025-10-24 23:43:21', '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2020, '笔记管理', 0, 1, 'notes', 'notes/notes/index', NULL, 1, 0, 'C', '0', '0', NULL, '#', 'admin', '2025-10-30 08:02:57', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2021, '笔记编辑', 0, 1, 'notesEditor', 'notesEditor/notesEditor/index', NULL, 1, 0, 'C', '0', '0', '', '#', 'admin', '2025-12-01 20:03:14', 'admin', '2025-12-01 20:14:03', '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2022, '用户笔记主，每篇笔记必须归属于一个用户自定义的分类', 0, 1, 'note', 'notes/note/index', NULL, 1, 0, 'C', '1', '0', 'notes:note:list', '#', 'admin', '2025-12-02 16:46:02', 'admin', '2025-12-06 15:49:29', '用户笔记主，每篇笔记必须归属于一个用户自定义的分类菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2023, '用户笔记主，每篇笔记必须归属于一个用户自定义的分类查询', 2022, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'notes:note:query', '#', 'admin', '2025-12-02 16:46:02', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2024, '用户笔记主，每篇笔记必须归属于一个用户自定义的分类新增', 2022, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'notes:note:add', '#', 'admin', '2025-12-02 16:46:02', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2025, '用户笔记主，每篇笔记必须归属于一个用户自定义的分类修改', 2022, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'notes:note:edit', '#', 'admin', '2025-12-02 16:46:02', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2026, '用户笔记主，每篇笔记必须归属于一个用户自定义的分类删除', 2022, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'notes:note:remove', '#', 'admin', '2025-12-02 16:46:02', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2027, '用户笔记主，每篇笔记必须归属于一个用户自定义的分类导出', 2022, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'notes:note:export', '#', 'admin', '2025-12-02 16:46:02', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2028, '笔记分类', 0, 1, 'noteCategory', 'noteCategory/noteCategory/index', NULL, 1, 0, 'C', '0', '0', 'noteCategory:noteCategory:list', '#', 'admin', '2025-12-02 20:42:33', 'admin', '2025-12-02 20:45:42', '笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2029, '笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记查询', 2028, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'noteCategory:noteCategory:query', '#', 'admin', '2025-12-02 20:42:33', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2030, '笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记新增', 2028, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'noteCategory:noteCategory:add', '#', 'admin', '2025-12-02 20:42:33', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2031, '笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记修改', 2028, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'noteCategory:noteCategory:edit', '#', 'admin', '2025-12-02 20:42:33', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2032, '笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记删除', 2028, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'noteCategory:noteCategory:remove', '#', 'admin', '2025-12-02 20:42:33', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2033, '笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记导出', 2028, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'noteCategory:noteCategory:export', '#', 'admin', '2025-12-02 20:42:33', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2040, '轮播图管理', 0, 1, 'carousel', 'carousel/carousel/index', NULL, 1, 0, 'C', '0', '0', 'carousel:carousel:list', '#', 'admin', '2025-12-05 19:44:55', 'admin', '2025-12-05 19:46:29', '轮播图管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2041, '轮播图管理查询', 2040, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'carousel:carousel:query', '#', 'admin', '2025-12-05 19:44:55', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2042, '轮播图管理新增', 2040, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'carousel:carousel:add', '#', 'admin', '2025-12-05 19:44:55', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2043, '轮播图管理修改', 2040, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'carousel:carousel:edit', '#', 'admin', '2025-12-05 19:44:55', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2044, '轮播图管理删除', 2040, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'carousel:carousel:remove', '#', 'admin', '2025-12-05 19:44:55', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2045, '轮播图管理导出', 2040, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'carousel:carousel:export', '#', 'admin', '2025-12-05 19:44:55', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2046, '题库管理', 0, 1, 'questionBank', 'questionBank/questionBank/index', NULL, 1, 0, 'C', '0', '0', 'questionBank:questionBank:list', '#', 'admin', '2025-12-06 15:57:27', 'admin', '2025-12-19 20:17:08', '题库主菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2047, '题库主查询', 2046, 1, '#', '', NULL, 1, 0, 'F', '1', '0', 'questionBank:questionBank:query', '#', 'admin', '2025-12-06 15:57:27', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2048, '题库主新增', 2046, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionBank:questionBank:add', '#', 'admin', '2025-12-06 15:57:27', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2049, '题库主修改', 2046, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionBank:questionBank:edit', '#', 'admin', '2025-12-06 15:57:27', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2050, '题库主删除', 2046, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionBank:questionBank:remove', '#', 'admin', '2025-12-06 15:57:27', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2051, '题库主导出', 2046, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionBank:questionBank:export', '#', 'admin', '2025-12-06 15:57:27', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2052, '一级题目', 0, 1, 'questionMain', 'questionMain/questionMain/index', NULL, 1, 0, 'C', '0', '0', 'questionMain:questionMain:list', '#', 'admin', '2025-12-06 21:04:54', '', NULL, '一级题目菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2053, '一级题目查询', 2052, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMain:questionMain:query', '#', 'admin', '2025-12-06 21:04:54', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2054, '一级题目新增', 2052, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMain:questionMain:add', '#', 'admin', '2025-12-06 21:04:54', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2055, '一级题目修改', 2052, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMain:questionMain:edit', '#', 'admin', '2025-12-06 21:04:54', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2056, '一级题目删除', 2052, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMain:questionMain:remove', '#', 'admin', '2025-12-06 21:04:54', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2057, '一级题目导出', 2052, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMain:questionMain:export', '#', 'admin', '2025-12-06 21:04:54', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2060, '收藏管理', 0, 1, 'manage', NULL, NULL, 1, 0, 'M', '0', '0', '', '#', 'admin', '2025-12-09 16:05:49', 'admin', '2025-12-09 16:11:23', '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2069, '用户题库收藏', 2060, 1, 'favoriteBank', 'favoriteBank/favoriteBank/index', NULL, 1, 0, 'C', '0', '0', 'favoriteBank:favoriteBank:list', '#', 'admin', '2025-12-09 22:01:05', '', NULL, '用户题库收藏菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2070, '用户题库收藏查询', 2069, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteBank:favoriteBank:query', '#', 'admin', '2025-12-09 22:01:05', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2071, '用户题库收藏新增', 2069, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteBank:favoriteBank:add', '#', 'admin', '2025-12-09 22:01:05', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2072, '用户题库收藏修改', 2069, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteBank:favoriteBank:edit', '#', 'admin', '2025-12-09 22:01:05', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2073, '用户题库收藏删除', 2069, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteBank:favoriteBank:remove', '#', 'admin', '2025-12-09 22:01:05', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2074, '用户题库收藏导出', 2069, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteBank:favoriteBank:export', '#', 'admin', '2025-12-09 22:01:05', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2075, '用户题目收藏', 2060, 1, 'favoriteQuestion', 'favoriteQuestion/favoriteQuestion/index', NULL, 1, 0, 'C', '0', '0', 'favoriteQuestion:favoriteQuestion:list', '#', 'admin', '2025-12-10 16:33:53', 'admin', '2025-12-10 16:36:53', '用户题目收藏（支持复习功能）菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2076, '用户题目收藏（支持复习功能）查询', 2075, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteQuestion:favoriteQuestion:query', '#', 'admin', '2025-12-10 16:33:53', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2077, '用户题目收藏（支持复习功能）新增', 2075, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteQuestion:favoriteQuestion:add', '#', 'admin', '2025-12-10 16:33:53', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2078, '用户题目收藏（支持复习功能）修改', 2075, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteQuestion:favoriteQuestion:edit', '#', 'admin', '2025-12-10 16:33:53', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2079, '用户题目收藏（支持复习功能）删除', 2075, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteQuestion:favoriteQuestion:remove', '#', 'admin', '2025-12-10 16:33:53', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2080, '用户题目收藏（支持复习功能）导出', 2075, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'favoriteQuestion:favoriteQuestion:export', '#', 'admin', '2025-12-10 16:33:53', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2085, '用户错题管理', 0, 1, 'questionError', 'questionError/questionError/index', NULL, 1, 0, 'C', '0', '0', 'questionError:questionError:list', '#', 'admin', '2025-12-16 20:56:43', 'admin', '2025-12-16 21:00:31', '用户错题记录（支持复习与掌握跟踪）菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2086, '用户错题记录（支持复习与掌握跟踪）查询', 2085, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionError:questionError:query', '#', 'admin', '2025-12-16 20:56:43', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2087, '用户错题记录（支持复习与掌握跟踪）新增', 2085, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionError:questionError:add', '#', 'admin', '2025-12-16 20:56:43', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2088, '用户错题记录（支持复习与掌握跟踪）修改', 2085, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionError:questionError:edit', '#', 'admin', '2025-12-16 20:56:43', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2089, '用户错题记录（支持复习与掌握跟踪）删除', 2085, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionError:questionError:remove', '#', 'admin', '2025-12-16 20:56:43', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2090, '用户错题记录（支持复习与掌握跟踪）导出', 2085, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionError:questionError:export', '#', 'admin', '2025-12-16 20:56:43', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2091, '用户斩题管理', 0, 1, 'questionMarked', 'questionMarked/questionMarked/index', NULL, 1, 0, 'C', '0', '0', 'questionMarked:questionMarked:list', '#', 'admin', '2025-12-17 20:19:45', 'admin', '2025-12-17 20:21:31', '用户斩题（重点攻克题目）菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2092, '用户斩题（重点攻克题目）查询', 2091, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMarked:questionMarked:query', '#', 'admin', '2025-12-17 20:19:45', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2093, '用户斩题（重点攻克题目）新增', 2091, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMarked:questionMarked:add', '#', 'admin', '2025-12-17 20:19:45', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2094, '用户斩题（重点攻克题目）修改', 2091, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMarked:questionMarked:edit', '#', 'admin', '2025-12-17 20:19:45', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2095, '用户斩题（重点攻克题目）删除', 2091, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMarked:questionMarked:remove', '#', 'admin', '2025-12-17 20:19:45', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2096, '用户斩题（重点攻克题目）导出', 2091, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'questionMarked:questionMarked:export', '#', 'admin', '2025-12-17 20:19:45', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2105, '敏感词管理', 0, 1, 'sensitiveWord', 'sensitiveWord/sensitiveWord/index', NULL, 1, 0, 'C', '0', '0', 'sensitiveWord:sensitiveWord:list', '#', 'admin', '2026-04-17 10:18:10', 'admin', '2026-04-17 10:22:36', '敏感词管理菜单');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2106, '敏感词管理查询', 2105, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'sensitiveWord:sensitiveWord:query', '#', 'admin', '2026-04-17 10:18:10', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2107, '敏感词管理新增', 2105, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'sensitiveWord:sensitiveWord:add', '#', 'admin', '2026-04-17 10:18:10', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2108, '敏感词管理修改', 2105, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'sensitiveWord:sensitiveWord:edit', '#', 'admin', '2026-04-17 10:18:10', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2109, '敏感词管理删除', 2105, 4, '#', '', NULL, 1, 0, 'F', '0', '0', 'sensitiveWord:sensitiveWord:remove', '#', 'admin', '2026-04-17 10:18:10', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2110, '敏感词管理导出', 2105, 5, '#', '', NULL, 1, 0, 'F', '0', '0', 'sensitiveWord:sensitiveWord:export', '#', 'admin', '2026-04-17 10:18:10', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2111, '留言管理', 0, 0, 'message', 'message/index', NULL, 1, 0, 'C', '0', '0', 'system:message:list', 'edit', 'admin', '2026-05-03 10:52:10', 'admin', '2026-05-03 11:21:22', '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2112, '留言删除', 2111, 1, '#', '', '', 1, 0, 'F', '0', '0', 'system:message:remove', '#', 'admin', '2026-05-03 11:27:30', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2113, '留言新增', 2111, 2, '#', '', '', 1, 0, 'F', '0', '0', 'system:message:add', '#', 'admin', '2026-05-03 11:28:28', '', NULL, '');
INSERT INTO public.sys_menu (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark) VALUES (2114, '留言修改', 2111, 3, '#', '', '', 1, 0, 'F', '0', '0', 'system:message:edit', '#', 'admin', '2026-05-03 11:28:28', '', NULL, '');


--
-- Data for Name: sys_role_menu; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (1, 2111);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (1, 2112);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (1, 2113);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (1, 2114);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2006);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2007);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2008);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2009);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2010);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2011);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2018);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2021);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2111);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2112);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2113);
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (2, 2114);


--
-- Name: sys_menu_menu_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.sys_menu_menu_id_seq', 2114, true);


-- ============================================================
-- ③ 演示数据
-- ============================================================
-- ============================================================
-- OpenStudy 部署种子数据（含演示数据，已清洗所有真实密钥/隐私）
-- ------------------------------------------------------------
-- ⚠️ 本文件**不含任何真实 API Key / 账号密码 / 隐私数据**：
--    · sys_ai_config 的 api_key 一律为占位符 'YOUR_API_KEY_HERE'，请部署后自行填写；
--    · sys_user 仅保留演示账号，密码均为 bcrypt('admin123')（首次登录后请立刻改密）；
--    · 业务内容（题库/题目/笔记）为少量演示数据。
-- 执行顺序：01_schema.sql → 02_seed.sql（本文件）。
-- ============================================================

-- ---------- 演示用户（密码统一 = admin123） ----------
INSERT INTO public.sys_user (user_id, user_name, nick_name, email, phonenumber, sex, avatar, password, status, del_flag, login_ip, login_date, dept_id, create_by, create_time, update_by, update_time, remark) VALUES
(1, 'admin', '管理员',   'admin@example.com', '15888888888', '1', '', '$2b$12$XCWtkQ37WqBbWgMklX2of.qe6Lps5fXh5ehMUr3zJ6fMe62QQahlW', '0', '0', '127.0.0.1', now(), 103, 'admin', now(), '', NULL, '演示超级管理员'),
(2, 'demo',  '演示用户', 'demo@example.com',  '15666666666', '0', '', '$2b$12$XCWtkQ37WqBbWgMklX2of.qe6Lps5fXh5ehMUr3zJ6fMe62QQahlW', '0', '0', '127.0.0.1', now(), 105, 'admin', now(), '', NULL, '演示普通用户');

-- ---------- 用户角色（1=超级管理员 admin，2=普通角色 common） ----------
INSERT INTO public.sys_user_role (user_id, role_id) VALUES
(1, 1),
(2, 2);

-- ---------- AI 模型配置（⚠️ 全部为占位 Key，部署后请自行填写） ----------
INSERT INTO public.sys_ai_config (config_id, user_id, provider, provider_name, model, api_key, base_url, web_phone, web_password, web_area_code, is_default, is_enabled, status, remark, thinking_mode, reasoning_effort, context_length, create_time, update_time, create_by, update_by, model_kind) VALUES
(1, NULL, 'deepseek', 'DeepSeek', 'deepseek-flash', 'YOUR_API_KEY_HERE', 'https://api.deepseek.com', NULL, NULL, NULL, 1, 1, '0', '默认对话模型（请填写 API Key）', 'auto', NULL, NULL, now(), NULL, 'admin', '', 'official'),
(2, NULL, 'deepseek', 'DeepSeek', 'deepseek-v4-pro', 'YOUR_API_KEY_HERE', 'https://api.deepseek.com', NULL, NULL, NULL, 0, 1, '0', '高级模型（请填写 API Key）', 'auto', NULL, NULL, now(), NULL, 'admin', '', 'official');

-- ---------- 系统通知（演示） ----------
INSERT INTO public.sys_notice (notice_id, notice_title, notice_type, notice_content, status, create_by, create_time, update_by, update_time, remark) VALUES
(1, '欢迎使用 OpenStudy', '1', '<p>欢迎使用 OpenStudy 开源学习平台。请先在「系统管理 → AI 模型配置」里填写你的 API Key。</p>', '0', 'admin', now(), '', NULL, NULL),
(2, '系统上线公告', '2', '<p>本环境为演示环境，数据仅供体验。</p>', '0', 'admin', now(), '', NULL, NULL);

-- ---------- 演示题库 ----------
INSERT INTO public.question_bank (id, bank_name, subject, description, cover_image, total_questions, status, user_id, create_time, is_public, allow_fork) VALUES
(1, '演示题库 · 数学基础', '数学', '用于演示的数学基础题题库', '', 2, '0', 1, now(), 1, 1),
(2, '演示题库 · 英语词汇', '英语', '用于演示的英语词汇题库', '', 1, '0', 1, now(), 1, 1);

-- ---------- 演示题目 ----------
INSERT INTO public.question_main (id, bank_id, question_type, difficulty, question_text, content, options, answer, analysis, has_sub_questions, sort_order, score, status, create_time) VALUES
(1, 1, 1, 1, '1 + 1 = ?', '1 + 1 = ?', NULL, '2', '基础加法。', 0, 0, 5.00, '0', now()),
(2, 1, 1, 1, '3 × 4 = ?', '3 × 4 = ?', NULL, '12', '基础乘法。', 0, 1, 5.00, '0', now()),
(3, 2, 1, 1, '“苹果”的英文是？', '“苹果”的英文是？', NULL, 'apple', '常见名词。', 0, 0, 5.00, '0', now());

-- ---------- 演示笔记分类 / 笔记 ----------
INSERT INTO public.note_category (id, user_id, name, order_num, create_time) VALUES
(1, 1, '默认分类', 0, now());

INSERT INTO public.note (note_id, user_id, category_id, title, filename, content, markdown_content, tags, is_public, view_count, like_count, comment_count, status, del_flag, create_time, update_time) VALUES
(1, 1, 1, '欢迎使用 OpenStudy 笔记', '', '这是一条演示笔记，你可以在「我的笔记」里自由编辑。', '这是一条演示笔记，你可以在「我的笔记」里自由编辑。', '', 0, 0, 0, 0, '0', '0', now(), NULL);
