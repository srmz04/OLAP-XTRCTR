// src/types/olap.ts
export interface Catalog {
    code: string;
    name: string;
    year: number;
}

export interface Member {
    caption: string;
    unique_name: string;
    level_name: string;
    children_cardinality: number;
    parent_unique_name?: string;
}

export interface Apartado extends Member {
    level_name: 'Apartado';
}

export interface Variable extends Member {
    level_name: 'Variable';
}

export interface CatalogsResponse {
    catalogs: Catalog[];
    count: number;
    timestamp: string;
}

export interface MembersResponse {
    catalog: string;
    nivel: string;
    members: Member[];
    count: number;
    total: number;
    limit: number;
    offset: number;
    timestamp: string;
}
